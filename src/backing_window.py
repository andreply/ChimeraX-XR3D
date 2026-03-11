# vim: set expandtab shiftwidth=4 softtabstop=4:

"""XR 3D interaction: enhanced backing window with 3D cursor, selection, and hover.

This module provides an enhanced backing window for ALL OpenXR autostereo
displays (Sony Spatial Reality, Acer SpatialLabs, Samsung Odyssey 3D).
It extends the upstream XRBackingWindow with:

- 3D cursor tracking at stereo depth (multiple styles via ``xr3d cursor`` command)
- 3D selection rectangle for ctrl+drag region selection
- 3D hover labels for atoms, residues, and bonds

The enable_xr3d_mouse_modes() entry point is called by the monkey-patched
_enable_xr_mouse_modes in __init__.py, which is invoked by ALL display
setup functions (Sony, Acer, Samsung).
"""

import time

from .cursor3d import Cursor3D, SelectionRect3D, CURSOR_STYLES


def enable_xr3d_mouse_modes(session, screen_model_name=None,
                             openxr_window_captures_events=False,
                             direct_pick=False):
    """Create an XR3DBackingWindow on the XR display.

    Called from the monkey-patched _enable_xr_mouse_modes for all
    display types. Parameters are passed through from the original
    display setup function.
    """
    from chimerax.xr3d import _get_xr_screens
    xr_screens = _get_xr_screens()
    if xr_screens is None:
        session.logger.warning('ChimeraX-XR3D: xr_screens not found.')
        return False
    screen = xr_screens.find_xr_screen(session, screen_model_name)
    if screen is None:
        session.logger.warning('Could not enable mouse on OpenXR screen.')
        return False
    XR3DBackingWindow(session, screen,
                      in_front=openxr_window_captures_events,
                      direct_pick=direct_pick)
    session.logger.status(
        f'ChimeraX-XR3D: 3D cursor enabled on "{screen.model()}"')
    return True


class XR3DBackingWindow:
    """Backing window for OpenXR autostereo displays with full 3D interaction.

    Works on all XR displays (Sony, Acer, Samsung). Creates a fullscreen
    Qt window on the display to capture mouse/keyboard events, with:
    - 3D cursor at correct stereo depth
    - 3D selection rectangle for ctrl+drag
    - 3D hover labels for atoms/residues/bonds
    - Optional direct_pick coordinate mapping (vrto3d)
    """

    def __init__(self, session, screen, in_front=False, direct_pick=False):
        self._session = session
        self._screen = screen
        self._cursor = None
        self._sel_rect = None
        self._sel_start = None
        self._sel_depth_point = None
        self._enabled = True

        # Pick throttling: only pick when mouse moves
        self._last_pick_xy = (None, None)

        # Create fullscreen backing Qt window on XR screen
        from Qt.QtWidgets import QWidget
        self._widget = w = QWidget()

        # Transparent, always on top when needed (vrto3d composites underneath)
        if in_front:
            self._make_transparent_in_front(w)

        w.move(screen.geometry().topLeft())
        w.showFullScreen()
        w.raise_()
        w.activateWindow()

        # Hover label state
        self._hover_pos = None
        self._hover_time = 0
        self._hover_active = False
        self._hover_label_object = (None, None)
        self._hover_shown_atoms = []
        self._hover_popup = self._create_hover_popup(w)

        # 3D cursor: hide OS cursor, render 3D shape at scene depth
        from Qt.QtCore import Qt
        w.setCursor(Qt.BlankCursor)
        w.setMouseTracking(True)
        self._cursor = Cursor3D(session)

        self._register_mouse_handlers()

        # Forward all key events to ChimeraX
        def key_press(event):
            session.ui.forward_keystroke(event)
        w.keyPressEvent = key_press

        # Clean up when XR stops
        self._vr_stopped_handler = session.triggers.add_handler(
            'vr stopped', self._xr_quit)

        # Hover labels via graphics update polling
        self._graphics_update_handler = session.triggers.add_handler(
            'graphics update', self._check_for_mouse_hover)

        # Register as active window for xr3d commands
        import chimerax.xr3d as _mod
        _mod._active_window = self

    def _make_transparent_in_front(self, w):
        """Make the backing window transparent and always-on-top.
        vrto3d/SteamVR composites the stereo view underneath this window."""
        from Qt.QtCore import Qt
        w.setAttribute(Qt.WA_TranslucentBackground)
        w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Translucent frameless windows don't capture mouse events without
        # a child frame that has a tiny bit of opacity.
        from Qt.QtWidgets import QFrame, QVBoxLayout
        self._f = f = QFrame(w)
        f.setStyleSheet("background: rgba(2, 2, 2, 2);")
        layout = QVBoxLayout(w)
        w.setLayout(layout)
        layout.addWidget(f)

    # -------------------------------------------------------------------
    # Enable / disable
    # -------------------------------------------------------------------

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value
        if self._widget is None:
            return
        from Qt.QtCore import Qt
        if value:
            self._widget.setCursor(Qt.BlankCursor)
            self._session.logger.info('ChimeraX-XR3D: 3D cursor enabled')
        else:
            self._widget.setCursor(Qt.ArrowCursor)
            if self._cursor is not None:
                self._cursor.hide()
            self._hide_hover_label()
            self._session.logger.info('ChimeraX-XR3D: 3D cursor disabled')

    def set_cursor_style(self, style):
        if self._cursor is not None:
            self._cursor.set_style(style)

    def set_cursor_size(self, radius):
        if self._cursor is not None:
            self._cursor.set_radius(radius)

    def set_cursor_color(self, color):
        if self._cursor is not None:
            self._cursor.set_color(color)

    def set_cursor_shadows(self, enabled):
        if self._cursor is not None:
            self._cursor.set_shadows(enabled)

    def reset_cursor_defaults(self):
        if self._cursor is not None:
            self._cursor.reset_defaults()

    # -------------------------------------------------------------------
    # Mouse event handling
    # -------------------------------------------------------------------

    def _register_mouse_handlers(self):
        w = self._widget
        w.mousePressEvent = self._mouse_down
        w.mouseMoveEvent = self._mouse_drag
        w.mouseReleaseEvent = self._mouse_up
        w.mouseDoubleClickEvent = self._mouse_double_click
        w.wheelEvent = self._wheel

    def _mouse_down(self, event):
        from Qt.QtCore import Qt
        if (self._enabled
                and event.button() == Qt.LeftButton
                and event.modifiers() & Qt.ControlModifier):
            p = event.position()
            gx, gy = self._backing_to_render_coordinates(p.x(), p.y())
            self._sel_start = (gx, gy)
            # Use cursor's last pick depth for selection plane
            self._sel_depth_point = (
                self._cursor.last_pick_position
                if self._cursor else None)
            if self._sel_rect is None:
                self._sel_rect = SelectionRect3D(self._session)
        self._dispatch_mouse_event(event, "mouse_down")

    def _mouse_drag(self, event):
        if event.buttons():
            from Qt.QtCore import Qt
            if (self._sel_start is not None
                    and event.buttons() & Qt.LeftButton):
                p = event.position()
                gx, gy = self._backing_to_render_coordinates(p.x(), p.y())
                self._sel_rect.update(
                    self._sel_start[0], self._sel_start[1], gx, gy,
                    depth_point=self._sel_depth_point)
            self._dispatch_mouse_event(event, "mouse_drag")

    def _mouse_up(self, event):
        if self._sel_start is not None:
            self._sel_start = None
            self._sel_depth_point = None
            if self._sel_rect is not None:
                self._sel_rect.hide()
        self._dispatch_mouse_event(event, "mouse_up")

    def _mouse_double_click(self, event):
        self._dispatch_mouse_event(event, "mouse_double_click")

    def _wheel(self, event):
        self._dispatch_wheel_event(event)

    def _dispatch_mouse_event(self, event, action):
        """Convert mouse event from backing window to render coordinates
        and dispatch to ChimeraX mouse modes."""
        p = event.position()
        gx, gy = self._backing_to_render_coordinates(p.x(), p.y())
        e = self._repositioned_event(event, gx, gy)
        mm = self._session.ui.mouse_modes
        mm._dispatch_mouse_event(e, action)

    def _dispatch_wheel_event(self, event):
        """Convert wheel event and dispatch."""
        p = event.position()
        gx, gy = self._backing_to_render_coordinates(p.x(), p.y())
        e = self._repositioned_event(event, gx, gy)
        mm = self._session.ui.mouse_modes
        mm._wheel_event(e)

    # -------------------------------------------------------------------
    # Coordinate mapping
    # -------------------------------------------------------------------

    def _backing_to_graphics_coordinates(self, x, y):
        """Convert backing window pixel coordinates to main graphics
        window coordinates, handling different aspect ratios."""
        w3d = self._widget
        w, h = w3d.width(), w3d.height()
        gw, gh = self._session.main_view.window_size
        if w == 0 or h == 0 or gw == 0 or gh == 0:
            return x, y
        fx, fy = x/w, y/h
        af = w*gh/(h*gw)
        if af > 1:
            afx = 0.5 + af * (fx - 0.5)
            afy = fy
        else:
            afx = fx
            afy = 0.5 + (1/af) * (fy - 0.5)
        gx, gy = afx * gw, afy * gh
        return gx, gy

    def _backing_to_render_coordinates(self, x, y):
        """Map backing window coordinates directly to the XR per-eye
        render texture, bypassing the graphics pane aspect ratio
        correction.  Needed for vrto3d where per-eye render is portrait
        (e.g. 1920x2160) but the graphics pane is landscape."""
        w3d = self._widget
        w, h = w3d.width(), w3d.height()
        if w == 0 or h == 0:
            return x, y
        cam = self._session.main_view.camera
        td = getattr(cam, '_texture_drawing', None)
        if td is None or td.texture is None:
            return self._backing_to_graphics_coordinates(x, y)
        fx, fy = x / w, y / h
        tc = td.texture_coordinates
        (xmin, ymin), (xmax, ymax) = tc[0], tc[2]
        gw, gh = self._session.main_view.window_size
        if (xmax - xmin) == 0 or (ymax - ymin) == 0:
            return self._backing_to_graphics_coordinates(x, y)
        gx = (fx - xmin) / (xmax - xmin) * gw
        gy = (fy - ymin) / (ymax - ymin) * gh
        return gx, gy

    def _repositioned_event(self, event, x, y):
        """Create a new Qt event with repositioned coordinates."""
        from Qt.QtGui import QMouseEvent, QWheelEvent
        from Qt.QtCore import QPointF
        pos = QPointF(x, y)
        if isinstance(event, QMouseEvent):
            return QMouseEvent(
                event.type(), pos, event.globalPosition(),
                event.button(), event.buttons(), event.modifiers(),
                event.device())
        elif isinstance(event, QWheelEvent):
            return QWheelEvent(
                pos, event.globalPosition(), event.pixelDelta(),
                event.angleDelta(), event.buttons(), event.modifiers(),
                event.phase(), event.inverted(), device=event.device())
        raise RuntimeError(f'Unexpected event type: {event}')

    # -------------------------------------------------------------------
    # Cursor + hover labels (per-frame update)
    # -------------------------------------------------------------------

    def _check_for_mouse_hover(self, *args):
        """Called each graphics frame.  Updates 3D cursor (throttled)
        and checks for mouse pause to show hover labels."""
        if self._widget is None:
            return 'delete handler'
        # Session close removes models without firing 'vr stopped'.
        if self._cursor is not None and self._cursor.deleted:
            self._cursor = None
            self._sel_rect = None
            self._widget.deleteLater()
            self._widget = None
            return 'delete handler'

        if not self._enabled:
            return

        from Qt.QtGui import QCursor
        cp = QCursor.pos()
        if self._session.ui.topLevelAt(cp) != self._widget:
            if self._cursor is not None:
                self._cursor.hide()
            return

        bp = self._widget.mapFromGlobal(cp)
        x, y = self._backing_to_render_coordinates(bp.x(), bp.y())
        ix, iy = int(x), int(y)

        # Cursor: pick only when mouse moves, otherwise just refresh
        # orientation for head tracking (no expensive ray-cast).
        now = time.time()
        if self._cursor is not None:
            if (ix, iy) != self._last_pick_xy:
                self._cursor.update(x, y)
                self._last_pick_xy = (ix, iy)
            else:
                self._cursor.refresh()

        # Hover labels: detect pause (0.7s threshold)
        if self._hover_pos != (ix, iy):
            self._hover_pos = (ix, iy)
            self._hover_time = now
            if self._hover_active:
                self._hover_active = False
                self._hide_hover_label()
        elif not self._hover_active and (now - self._hover_time) > 0.7:
            self._hover_active = True
            pick, obj, label_type = self._hover_pick(x, y)
            if pick is None:
                self._hide_hover_label()
            else:
                self._show_hover_label(pick, obj, label_type, x, y)

    def _create_hover_popup(self, parent):
        """Create a 2D text popup for hover labels, like the normal GUI."""
        from Qt.QtWidgets import QLabel
        from Qt.QtCore import Qt
        popup = QLabel(parent)
        popup.setStyleSheet(
            'QLabel {'
            '  background: rgba(0, 0, 0, 200);'
            '  color: white;'
            '  padding: 4px 8px;'
            '  border-radius: 4px;'
            '  font-size: 14px;'
            '}')
        popup.setAttribute(Qt.WA_TransparentForMouseEvents)
        popup.hide()
        return popup

    def _hover_pick(self, x, y):
        pick = self._session.main_view.picked_object(x, y)
        if pick is None:
            return None, None, None
        from chimerax.atomic import PickedAtom, PickedResidue, PickedBond
        from chimerax.core.objects import Objects
        if isinstance(pick, PickedAtom):
            from chimerax.atomic import Atoms
            obj = Objects(atoms=Atoms([pick.atom]))
            label_type = 'atoms'
        elif isinstance(pick, PickedResidue):
            obj = Objects(atoms=pick.residue.atoms)
            label_type = 'residues'
        elif isinstance(pick, PickedBond):
            from chimerax.atomic import Bonds
            obj = Objects(bonds=Bonds([pick.bond]))
            label_type = 'bonds'
        else:
            # Surfaces, maps, etc. — find nearest atom for 3D label
            atom = self._nearest_atom(pick)
            if atom is not None:
                from chimerax.atomic import Atoms
                obj = Objects(atoms=Atoms([atom]))
                label_type = 'atoms'
            else:
                obj = None
                label_type = None
        return pick, obj, label_type

    def _nearest_atom(self, pick):
        """Find the closest atom to a pick's 3D position."""
        pos = getattr(pick, 'position', None)
        if pos is None:
            return None
        from chimerax.atomic import all_atoms
        atoms = all_atoms(self._session)
        if len(atoms) == 0:
            return None
        from numpy.linalg import norm
        dists = norm(atoms.scene_coords - pos, axis=1)
        return atoms[dists.argmin()]

    def _show_hover_label(self, pick, obj, label_type, x, y):
        text = pick.description()
        if obj is not None:
            # Temporarily show hidden atoms so label3d renders the label.
            self._hover_shown_atoms = []
            if label_type == 'atoms' and hasattr(obj, 'atoms'):
                for a in obj.atoms:
                    if not a.display:
                        a.display = True
                        self._hover_shown_atoms.append(a)
            from chimerax.label.label3d import label
            label(self._session, obj, label_type,
                  text=text, bg_color=(0, 0, 0, 255))
            self._hover_label_object = obj, label_type
        else:
            # No atom available — fall back to 2D popup
            self._hover_popup.setText(text)
            self._hover_popup.adjustSize()
            px = int(x * self._widget.width()
                     / self._session.main_view.window_size[0]) + 16
            py = int(y * self._widget.height()
                     / self._session.main_view.window_size[1]) - 10
            pw, ph = self._hover_popup.width(), self._hover_popup.height()
            ww, wh = self._widget.width(), self._widget.height()
            if px + pw > ww:
                px = max(0, px - pw - 32)
            if py < 0:
                py = 0
            elif py + ph > wh:
                py = wh - ph
            self._hover_popup.move(px, py)
            self._hover_popup.show()
        self._session.logger.status(text)

    def _hide_hover_label(self):
        # Hide 3D label
        obj, label_type = self._hover_label_object
        if obj is not None:
            from chimerax.label.label3d import label_delete
            label_delete(self._session, obj, label_type)
            for a in self._hover_shown_atoms:
                a.display = False
            self._hover_shown_atoms = []
        self._hover_label_object = (None, None)
        # Hide 2D popup
        if self._hover_popup is not None:
            self._hover_popup.hide()

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------

    def _xr_quit(self, *args):
        # Remove graphics update handler first to stop hover/cursor updates
        from chimerax.core.triggerset import DEREGISTER
        if self._graphics_update_handler is not None:
            self._session.triggers.remove_handler(
                self._graphics_update_handler)
            self._graphics_update_handler = None
        self._hide_hover_label()
        # Hide models immediately; defer removal to avoid race with
        # the render pass that can access positions during this trigger.
        if self._cursor is not None:
            self._cursor.hide()
        if self._sel_rect is not None:
            self._sel_rect.hide()
        if self._widget is not None:
            self._widget.hide()

        # Clear active window reference
        import chimerax.xr3d as _mod
        _mod._active_window = None

        def _deferred_cleanup(*args):
            if self._cursor is not None:
                self._cursor.delete()
                self._cursor = None
            if self._sel_rect is not None:
                self._sel_rect.delete()
                self._sel_rect = None
            if self._widget is not None:
                self._widget.deleteLater()
                self._widget = None
            return DEREGISTER

        self._session.triggers.add_handler('new frame', _deferred_cleanup)
        return DEREGISTER
