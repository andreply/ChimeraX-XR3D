# vim: set expandtab shiftwidth=4 softtabstop=4:
"""Persistent user preferences for ChimeraX-XR3D.

The 3D cursor's style, size, colour and shadow casting are all saved per user.
Set the cursor you like once and every later ``xr on`` brings it back.

Before this existed, all four lived only on the current ``Cursor3D`` object.
Every ``xr on`` built a fresh one from hardcoded constants, so a preference
could not be expressed durably -- it had to be re-typed each session.

Why shadows ship **off** while the others ship at their obvious values: shadow
casting forces a shadow-map rebuild whenever the cursor moves, which is
noticeable on slower GPUs.  The cost is real, so it is opt-in -- but it is a
*default*, not a prohibition, and a user who wants shadows should only have to
say so once.

``AUTO_SAVE`` means assignment writes straight to disk; there is no explicit
``save()`` call and no ``save true`` keyword for the user to remember.

These constants are the single source of truth for the shipped defaults.
``cursor3d`` imports them, and ``xr3d cursor default`` resets to them.
"""

from chimerax.core.settings import Settings

#: Shipped defaults.  Also what `xr3d cursor default` restores.
DEFAULT_STYLE = 'sphere'
DEFAULT_SIZE = 0.4
DEFAULT_COLOR = None      # None = the built-in auto-contrast orange gradient
DEFAULT_SHADOWS = False   # off: shadow-map rebuilds cost frames on slower GPUs

#: Label defaults live in labels3d, next to the code that explains them.
from .labels3d import (DEFAULT_DEPTH, DEFAULT_LIFT, DEFAULT_PLATE,
                       DEFAULT_PATCH_OFFSET, DEFAULT_MIN_AREA,
                       DEFAULT_MAX_TRAVEL)


class _XR3DSettings(Settings):
    AUTO_SAVE = {
        'cursor_style': DEFAULT_STYLE,
        'cursor_size': DEFAULT_SIZE,
        # Stored as a plain [r, g, b, a] list of ints, not a ChimeraX Color:
        # Settings persists values via repr(), and a list round-trips safely
        # where a Color object would need a custom Value() converter.
        'cursor_color': DEFAULT_COLOR,
        'cursor_shadows': DEFAULT_SHADOWS,
        'label_depth': DEFAULT_DEPTH,
        'label_lift': DEFAULT_LIFT,
        'label_plate': DEFAULT_PLATE,
        'label_patch_offset': DEFAULT_PATCH_OFFSET,
        'label_min_area': DEFAULT_MIN_AREA,
        'label_max_travel': DEFAULT_MAX_TRAVEL,
    }


_settings = None


def get_settings(session):
    """Return the singleton XR3D settings, creating it on first use.

    Deliberately lazy: constructing a Settings object touches the config file,
    and the bundle initialises at ChimeraX startup on machines that may have no
    XR display at all.
    """
    global _settings
    if _settings is None:
        _settings = _XR3DSettings(session, "ChimeraX-XR3D")
    return _settings


def saved_style(session):
    """The saved cursor style, falling back if a stored value is no longer legal.

    Guards the case where a preference was written by a version that had a style
    this build no longer ships -- a stale config should not break `xr on`.
    """
    from .cursor3d import CURSOR_STYLES
    style = get_settings(session).cursor_style
    return style if style in CURSOR_STYLES else DEFAULT_STYLE


def saved_color(session):
    """The saved cursor colour as an ``[r, g, b, a]`` list, or None for default."""
    rgba = get_settings(session).cursor_color
    if rgba is None:
        return None
    try:
        if len(rgba) == 4:
            return [int(c) for c in rgba]
    except TypeError:
        pass
    return None
