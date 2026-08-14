# XR backing window is scale-factor times too large on a fractionally scaled display

Draft for upstream (RBVI/ChimeraX). Everything below was measured on 2026-08-14.

---

## Summary

On a mixed-DPI multi-monitor setup, the fullscreen backing window created by
`XRBackingWindow` (`chimerax/vive/xr_screens.py`) comes out **1.5x too large in both
axes**: 5760x3240 native pixels for a 3840x2160 panel at 150% display scaling.

Because that window is transparent and always-on-top (`openxr_window_captures_events=True`
on the vrto3d path), the 1920 px overhang lies invisibly over the neighbouring monitor and
**silently swallows its mouse events**. Symptoms as experienced by the user:

- Dragging on the desktop *beside* the ChimeraX window rotates the molecule.
- The pointer cannot leave the 3D display, because it never actually leaves this window.
- Only the region under the overhang misbehaves, so it reads as "the wrong areas control
  the molecule", which is hard to attribute to a window nobody can see.

## Scope: this is not specific to one display or to vrto3d

`_enable_xr_mouse_modes()` is the single entry point used by **all** the autostereo setup
paths in `xr_screens.py` (Sony Spatial Reality, Acer SpatialLabs, Samsung Odyssey). Nothing
in the failing code is display-specific: it is a bare `QWidget`, a `move()` and a
`showFullScreen()`. Any of those displays, on a machine where the XR panel and another
monitor run at different scale factors, should hit it. A fractionally scaled 4K panel next
to a 1080p/1440p monitor at 100% is a common desktop, and Windows recommends 150% for a
27" 4K panel by default.

The vrto3d path is simply where we hit it, because `openxr_window_captures_events=True`
there makes the oversized window transparent and always-on-top, which turns a cosmetic
sizing error into silently stolen mouse input on the neighbouring monitor.

## Core already uses the pattern that avoids this, elsewhere

The Looking Glass bundle creates a fullscreen window on a secondary display too, and it
binds the window to the target screen **before** showing it, plus carries a Windows-specific
workaround for exactly this situation (`looking_glass/lookingglass.py:344`):

```python
screen = None if quilt else self._looking_glass_screen()
QWindow.__init__(self, screen = screen)          # bound at construction
...
if platform == 'win32':
    # Qt 5.12 hangs if OpenGL window is put on second display
    # but works if moved after a delay.
    self.setScreen(self._session.ui.primaryScreen())
    def _set_fullscreen(self=self, screen=screen):
        self.setScreen(screen)                   # bind, then fullscreen
        self.showFullScreen()
```

`xr_screens.py` does neither. It constructs a bare `QWidget`, `move()`s it to a device-pixel
coordinate and calls `showFullScreen()`:

```python
self._widget = w = QWidget()
...
w.move(screen.geometry().topLeft())
w.showFullScreen()
```

**Suggested direction:** make the XR backing window bind to the target `QScreen` before it
is shown, as Looking Glass does. In our testing that was the only change that produced a
window with no scale mismatch at all (details under "Lead" below). We have not verified
that the Looking Glass path is itself immune, having no such device here, so we offer this
as a difference in approach rather than a claim about that bundle.

## Environment

| | |
|---|---|
| ChimeraX | 1.13.dev202606030000 |
| OS | Windows 11 Pro 26200 |
| XR display | 4K 27" autostereo panel, 3840x2160, **150% scaling**, primary, at (0,0) |
| Second display | 2560x1440, **100% scaling**, at (3840,321) |
| XR path | `_enable_xr_mouse_modes` with `openxr_window_captures_events=True`, `direct_pick=True` |
| Process DPI awareness | `PROCESS_PER_MONITOR_DPI_AWARE` (queried via `GetProcessDpiAwareness`) |

## Reproduce

1. Two monitors at different scale factors, the XR display on the fractional one.
2. `xr on`.
3. Measure the backing window with `GetWindowRect` from a per-monitor-DPI-aware process.

## Expected vs actual

```
expected native : 3840 x 2160   (exactly the panel)
actual native   : 5760 x 3240   (overhangs 1920 px onto the next monitor)
```

## The numbers, from Qt itself

Queried live via `QApplication.topLevelWidgets()` while the window was up:

```
backing QWidget
   geometry (logical) : 3840x2160 @ (0,0)     <-- the defect
   devicePixelRatio   : 1.5
   QWindow.geometry   : 3840x2160 @ (0,0)
   on QScreen "Odyssey G90XF" : 2560x1440 @ (0,0)  dpr=1.5
   expected native    : 3840 * 1.5 = 5760 x 3240   <-- matches Windows exactly
```

**Qt is self-consistent throughout.** The single wrong value is the widget's *logical*
geometry: it is 3840x2160 when the screen is 2560x1440 logical. 3840x2160 is precisely the
panel's device-pixel size, i.e. the value `screen.geometry()` returns, so a device-pixel
rect is ending up where a logical rect belongs.

## Control: plain `showFullScreen()` on the same display is correct

`ui fullscreen true` calls `self.showFullScreen()` on the main window (`ui/gui.py:1157`),
the same Qt call the XR path uses. With the main window moved onto the same 150%-scaled
panel and XR off:

```
main window, ui fullscreen true : 3840x2160 at (0,0)   <- correct, exactly the panel
XR backing window               : 5760x3240 at (0,0)   <- same call, same screen, wrong
```

So this is **not** a general "ChimeraX cannot go fullscreen on a scaled display" problem,
and not a Qt-is-broken-here problem. Fullscreen works correctly on that very monitor. The
difference is confined to how the XR backing window is constructed: a brand-new `QWidget`
created while the application's context is the *other* monitor, positioned with a
device-pixel coordinate, and only then shown fullscreen. The main window, which already
lives on the target screen, is sized correctly.

That is consistent with the "Lead" section below, and it is why the Looking Glass approach
of binding the window to its screen at construction looks like the right shape of fix.

A second control points the same way: **`vr on` is unaffected**, because it never creates
this window. With VR running, the only ChimeraX top-level window is the main window, on its
original monitor. So neither SteamVR rendering nor the OpenXR camera is implicated; only the
backing window created by `_enable_xr_mouse_modes` is.

## Ruled out

Each of these was tested and did **not** change the result:

| Attempt | Result |
|---|---|
| Uninstalling our third-party bundle entirely | unchanged, 5760x3240 (so this is core, not us) |
| `setGeometry(qscreen.geometry())` before `showFullScreen()` | overridden, unchanged |
| Removing `showFullScreen()` entirely, plain `show()` | unchanged |
| `setMaximumSize(qscreen.geometry().size())` before showing | Qt reports the right logical size, Windows still 5760x3240 |
| `windowHandle().setGeometry(...)` on the native QWindow | unchanged |
| Forcing `~ HIGHDPIAWARE` via Windows AppCompat | unchanged |
| Correcting geometry after the fact | works only in *some* runs, see below |

The after-the-fact correction is unreliable in an informative way: whether Qt reports a
geometry that differs from the QScreen rect **varies between runs of identical code**. In
runs where it differs, a correction fires and the window is right; in runs where Qt already
reports the window as matching the screen, there is nothing to detect while Windows still
renders it oversized.

## Lead

Binding the window to the target `QScreen` *before* sizing it produced, for the first time,
a **fully self-consistent window**: logical 2560x1440 at dpr 1.0, native size matching, no
double scaling anywhere.

```python
w.winId()                       # realise the native window
w.windowHandle().setScreen(qscreen)
w.setGeometry(qscreen.geometry())
```

That suggests the logical geometry is being corrupted by a **cross-screen DPI transition**:
the widget is created associated with the 1.0-scale monitor (where the main window lives)
and is then placed on the 1.5-scale monitor, and the geometry is rescaled by the ratio
(2560 -> 3840) rather than reinterpreted.

**Caveat, offered honestly:** in that test the window ended up on the *wrong monitor*. The
`showFullScreen()` that still followed appears to have re-placed it on the widget's original
screen. In a second run the log confirmed it had bound to the QScreen named
`Odyssey G90XF`, yet the window still landed on the other monitor's rect. So the screen
association itself is not behaving as expected here, and we did not chase that further.

## Impact

Any autostereo XR display on a fractionally scaled monitor, next to a monitor at a different
scale factor, on any of the three supported display families. The failure is silent: no
error, nothing visible, just a transparent window eating input on an adjacent display. It
took a full day to attribute, and the natural first suspicion falls on the third-party
display driver rather than on ChimeraX.

## Workaround

Set the XR display to 100% scaling. Then logical and device pixels coincide, the arithmetic
happens to be right, and the window is correct on every run (verified repeatedly).
