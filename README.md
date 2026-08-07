# ChimeraX-XR3D

3D cursor, selection, and hover labels for OpenXR autostereo displays in UCSF ChimeraX.

## Features

- **3D cursor** at correct stereo depth (5 styles: sphere, crosshair, diamond, arrow, cone)
- **3D selection rectangle** for ctrl+drag region-based selection visible in stereo
- **3D hover labels** for atoms, residues, and bonds at proper scene depth
- **Shadow casting** — cursor casts shadow on molecules for depth cues
- **Custom colors** with auto-contrast gradient (smart inversion for dark colors)

Works on all OpenXR autostereo displays: Sony Spatial Reality, Acer SpatialLabs, Samsung Odyssey 3D (via vrto3d).

## Requirements

- UCSF ChimeraX daily build **2026-02-27 or newer** (includes the vrto3d base support merged upstream in February 2026)
- A supported OpenXR autostereo display:
  - Sony Spatial Reality (15.6" or 27")
  - Acer SpatialLabs
  - Samsung Odyssey 3D (G90XF 27" 4K or G90XH 32" 6K) via [vrto3d](https://github.com/oneup03/VRto3D) + SteamVR

## Install

From ChimeraX command line:

```
devel install /path/to/ChimeraX-XR3D
```

## Usage

1. Start ChimeraX, load a molecule (`open 1a0s`)
2. `xr on` — display shows stereo with 3D cursor
3. Move mouse over molecule — cursor appears at atom depth in 3D
4. **Ctrl+drag** for 3D selection rectangle
5. Hover on atoms/residues for 3D labels
6. `xr off` — clean up, OS cursor returns

### Commands

| Command | Description |
|---------|-------------|
| `xr3d cursor sphere` | Switch to sphere style (also: crosshair, diamond, arrow, cone) |
| `xr3d cursor default` | Reset style, size, and color to defaults |
| `xr3d cursor size 0.6` | Change cursor size (default 0.4) |
| `xr3d cursor color red` | Change cursor color (any ChimeraX color) |
| `xr3d shadows true` | Turn shadow casting on (off by default) |
| `xr3d cursor shadows true` | Same thing — kept for compatibility |
| `xr3d cursor cone size 0.8 color blue` | Combine style, size, and color |
| `xr3d on` / `xr3d off` | Enable/disable 3D cursor |

Command words, keywords and booleans can all be truncated once unambiguous, so
`xr3d sh on` is the same as `xr3d shadows true`.

### Your cursor is remembered

**Style, size, colour and shadows are all saved per user.** Set the cursor you like once
and every later `xr on` brings it back — before v0.10 they lived only on the current cursor
object, so each session started from the shipped defaults again.

```
xr3d cursor cone size 0.6 color cornflowerblue
xr3d shadows true
```

Storage is ChimeraX's own `Settings` (`AUTO_SAVE`), written the moment you change something —
there is no save step. To go back to the shipped defaults **and forget the saved values**:

```
xr3d cursor default
```

### Shadows

The cursor can cast a shadow onto the molecule, which makes its depth much easier to read.
It ships **off**, because shadow casting forces a shadow-map rebuild as the cursor moves and
that is noticeable on slower GPUs — the cost is real, so it is opt-in. It is a default, not a
limit: turn it on once and it stays on.

`xr3d shadows` works with **no XR session active**, so it can go in a startup script or be set
before the display is even connected.

## Architecture

ChimeraX Toolshed plugin that swaps `xr_screens`' backing window for one with 3D
interaction features, on all XR displays. It prefers the **public**
`enable_xr_mouse_modes` hook (ChimeraX ≥ 1.12.dev202603101234) and only falls back to
monkey-patching the private `_enable_xr_mouse_modes` on 1.11.

```
src/
  __init__.py         # Bundle API, commands, hook install/remove
  cursor3d.py         # Cursor3D, SelectionRect3D, geometry generators
  backing_window.py   # XR3DBackingWindow (mouse, hover, coordination)
  settings.py         # saved preferences + the shipped defaults
```

If ChimeraX ever gains a registration hook API upstream, the monkey-patching
can be replaced with a clean registration call.

## Technical Details

- **Vertex baking**: Cursor rotation is baked into vertex positions via `set_geometry()` each frame. Using `model.position = Place(axes=R)` does NOT work in ChimeraX's XR rendering pipeline — cursors rotate with the molecule instead of staying screen-fixed.
- **View rotation transpose**: `camera.view().axes()` gives scene-to-camera. We need camera-to-scene = `.axes().T` (transpose).
- **Direct pick** (vrto3d only): Per-eye render is portrait (1920x2160) while the screen is landscape. Standard coordinate mapping through the graphics pane loses accuracy. `_backing_to_render_coordinates` maps backing window coordinates to the XR render texture via inverted texture coordinates, falling back to standard mapping on other displays.

## Known Issues

- **Samsung Hub**: 3D overlay (Ctrl+Shift+2) conflicts with vrto3d SBS. Keep it OFF.
- **Auto-convert**: Samsung Hub auto-convert must be OFF — causes window focus issues.

## References

- [ChimeraX Bundle Development Guide](https://www.cgl.ucsf.edu/chimerax/docs/devel/writing_bundles.html)

## Author

[andreply](https://github.com/andreply)
