# vim: set expandtab shiftwidth=4 softtabstop=4:

from chimerax.core.toolshed import BundleAPI


class _XR3DInteractionAPI(BundleAPI):
    """Bundle API for 3D cursor, selection, and hover on XR displays.

    Uses the public enable_xr_mouse_modes hook in xr_screens (ChimeraX
    >= 1.12.dev202603101234) when available.  Falls back to monkey-
    patching _enable_xr_mouse_modes for ChimeraX 1.11.
    """
    api_version = 1

    @staticmethod
    def initialize(session, bi):
        """Called at ChimeraX startup (customInit=true)."""
        _install_hook(session)
        _register_commands(session)

    @staticmethod
    def finish(session, bi):
        """Called at ChimeraX shutdown."""
        _remove_hook()


# ---------------------------------------------------------------------------
# Active window reference (used by xr3d commands)
# ---------------------------------------------------------------------------

_active_window = None


# ---------------------------------------------------------------------------
# Commands: xr3d on, xr3d off, xr3d cursor <style>
# ---------------------------------------------------------------------------

def _register_commands(session):
    from chimerax.core.commands import (register, CmdDesc, EnumOf,
                                        FloatArg, ColorArg, BoolArg)
    from .cursor3d import CURSOR_STYLES

    style_arg = EnumOf((*CURSOR_STYLES, 'default'))
    cursor_desc = CmdDesc(
        optional=[('style', style_arg)],
        keyword=[('size', FloatArg),
                 ('color', ColorArg),
                 ('shadows', BoolArg)],
        synopsis='Set 3D cursor style, size, or color')
    register('xr3d cursor', cursor_desc, _cmd_cursor,
             logger=session.logger)

    on_desc = CmdDesc(synopsis='Enable 3D cursor on XR display')
    register('xr3d on', on_desc, _cmd_on, logger=session.logger)

    off_desc = CmdDesc(synopsis='Disable 3D cursor on XR display')
    register('xr3d off', off_desc, _cmd_off, logger=session.logger)


def _cmd_cursor(session, style=None, size=None, color=None, shadows=None):
    if _active_window is None:
        session.logger.warning('No active XR3D session')
        return
    if style is not None:
        if style == 'default':
            _active_window.reset_cursor_defaults()
            session.logger.info('3D cursor reset to defaults')
            return
        _active_window.set_cursor_style(style)
        session.logger.info(f'3D cursor style: {style}')
    if size is not None:
        _active_window.set_cursor_size(size)
        session.logger.info(f'3D cursor size: {size}')
    if color is not None:
        _active_window.set_cursor_color(color)
        session.logger.info(f'3D cursor color: {color}')
    if shadows is not None:
        _active_window.set_cursor_shadows(shadows)
        session.logger.info(
            f'3D cursor shadows: {"on" if shadows else "off"}')


def _cmd_on(session):
    if _active_window is not None:
        _active_window.enabled = True
    else:
        session.logger.warning(
            'No active XR3D session (use "xr on" first)')


def _cmd_off(session):
    if _active_window is not None:
        _active_window.enabled = False
    else:
        session.logger.warning('No active XR3D session')


# ---------------------------------------------------------------------------
# Hook infrastructure
# ---------------------------------------------------------------------------

_original_enable_xr_mouse_modes = None
_hook_method = None  # 'public' or 'monkey-patch'


def _get_xr_screens():
    """Import xr_screens from the correct location.
    Older builds have it at chimerax.vive, newer at chimerax.xr."""
    try:
        from chimerax.xr import xr_screens
        return xr_screens
    except ImportError:
        pass
    try:
        from chimerax.vive import xr_screens
        return xr_screens
    except ImportError:
        pass
    return None


def _install_hook(session):
    """Install our enhanced enable_xr_mouse_modes.

    Prefers the public enable_xr_mouse_modes hook (>= 1.12.dev202603101234).
    Falls back to monkey-patching _enable_xr_mouse_modes for ChimeraX 1.11.
    """
    global _original_enable_xr_mouse_modes, _hook_method
    if _original_enable_xr_mouse_modes is not None:
        return  # already installed
    xr_screens = _get_xr_screens()
    if xr_screens is None:
        session.logger.warning(
            'ChimeraX-XR3D: xr_screens module not found.')
        return

    # Add Samsung models if not already present
    for model in ('Odyssey G90XF', 'Odyssey G90XH'):
        if model not in xr_screens.xr_screen_model_names:
            xr_screens.xr_screen_model_names.append(model)

    # Try public hook first (>= 1.12.dev202603101234)
    if hasattr(xr_screens, 'enable_xr_mouse_modes'):
        _original_enable_xr_mouse_modes = xr_screens.enable_xr_mouse_modes
        xr_screens.enable_xr_mouse_modes = _enhanced_enable_xr_mouse_modes
        _hook_method = 'public'
    else:
        # Fallback: monkey-patch private method (ChimeraX 1.11)
        _original_enable_xr_mouse_modes = xr_screens._enable_xr_mouse_modes
        xr_screens._enable_xr_mouse_modes = _enhanced_enable_xr_mouse_modes
        _hook_method = 'monkey-patch'


def _remove_hook():
    """Restore original enable_xr_mouse_modes."""
    global _original_enable_xr_mouse_modes, _hook_method
    if _original_enable_xr_mouse_modes is not None:
        xr_screens = _get_xr_screens()
        if xr_screens is not None:
            if _hook_method == 'public':
                xr_screens.enable_xr_mouse_modes = _original_enable_xr_mouse_modes
            else:
                xr_screens._enable_xr_mouse_modes = _original_enable_xr_mouse_modes
        _original_enable_xr_mouse_modes = None
        _hook_method = None


def _enhanced_enable_xr_mouse_modes(session, screen_model_name=None,
                                     openxr_window_captures_events=False,
                                     direct_pick=False, **kwargs):
    """Enhanced _enable_xr_mouse_modes that creates our 3D-capable
    backing window instead of the vanilla XRBackingWindow.

    Called by all display setup functions (Sony, Acer, Samsung).
    Passes through direct_pick and openxr_window_captures_events
    from the original caller.
    """
    from .backing_window import enable_xr3d_mouse_modes
    result = enable_xr3d_mouse_modes(
        session,
        screen_model_name=screen_model_name,
        openxr_window_captures_events=openxr_window_captures_events,
        direct_pick=direct_pick)

    # vrto3d: fit scene to room so the molecule doesn't appear too low.
    # Sony/Acer call fit_view_to_room() in their own setup functions,
    # but vrto3d skips it, falling through to the default fit_scene_to_room()
    # which places the scene at (0,1,0) — often mismatched with vrto3d's
    # virtual head position.
    if direct_pick and result:
        _fit_vrto3d_view(session)

    return result


def _fit_vrto3d_view(session):
    """Fit vrto3d scene preserving the desktop camera view.

    Sony/Acer call fit_view_to_room() during setup because their drivers
    expose screen geometry. vrto3d doesn't, and the headset pose isn't
    available during setup either. So we:
    1. Save the desktop camera now (still active during setup)
    2. After the first XR frame, query the head pose
    3. Call fit_view_to_room() with the saved camera + head-derived geometry

    This makes the 3D stereo view match the 2D desktop view.
    """
    v = session.main_view
    saved_camera = v.camera
    saved_center = v.center_of_rotation.copy()

    def _on_first_frame(*args):
        cam = getattr(session, '_openxr_camera', None)
        if cam is None:
            return 'delete handler'

        xr = getattr(cam, '_xr', None)
        if xr is None:
            return 'delete handler'

        head_pose = xr.headset_pose()
        if head_pose is None:
            return  # try again next frame

        from numpy import array
        from math import tan, radians
        from chimerax.geometry import Place

        head = head_pose.origin()

        # Typical viewing distance for autostereo desktop monitors (meters).
        viewing_distance = 0.50
        vrto3d_fov = _get_vrto3d_fov()  # horizontal FOV in degrees

        # Compute room_width from vrto3d FOV so zoom matches desktop view.
        # Physical screen is 597mm, but vrto3d renders at 90° FOV which is
        # wider than the ~62° the physical screen subtends at 50cm.
        # The 0.084m offset is ~1/4 of the 27" screen height (336mm/4),
        # placing the scene center slightly behind the screen plane.
        center_distance = viewing_distance + 0.084
        room_width = 2 * center_distance * tan(radians(vrto3d_fov / 2))

        # Screen vertical, in front of head. Model slightly behind screen.
        screen_orientation = Place()
        model_center = array((float(head[0]),
                              float(head[1]),
                              float(head[2]) - center_distance))

        cam.fit_view_to_room(
            room_width=room_width,
            room_center=model_center,
            room_center_distance=center_distance,
            screen_orientation=screen_orientation,
            scene_center=saved_center,
            scene_camera=saved_camera)

        # Update defaults so that view_all / focus commands use the
        # correct head-relative room center instead of the default (0,1,0).
        cam._initial_room_center = model_center
        cam._initial_room_scene_size = room_width

        session.logger.status(
            f'ChimeraX-XR3D: vrto3d view fitted')
        return 'delete handler'

    session.triggers.add_handler('new frame', _on_first_frame)


def _get_vrto3d_fov():
    """Read horizontal FOV from vrto3d config. Falls back to 90°."""
    import os
    import json
    config_path = os.path.join(
        os.path.expanduser('~'), 'Documents', 'My Games',
        'vrto3d', 'default_config.json')
    try:
        with open(config_path) as f:
            return float(json.load(f).get('fov', 90.0))
    except Exception:
        return 90.0


bundle_api = _XR3DInteractionAPI()
