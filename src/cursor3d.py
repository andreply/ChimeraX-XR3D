# vim: set expandtab shiftwidth=4 softtabstop=4:

"""3D cursor for autostereo displays.

Renders a small shape in the scene at the depth of whatever is under
the mouse, so it appears at the correct stereo depth.

Orientation is baked into vertex positions each frame via set_geometry()
so it stays screen-fixed in XR rendering.  model.position handles
translation only — using Place(axes=R) does NOT work in the XR
rendering pipeline (cursors rotate with the molecule).
"""

import numpy as np

CURSOR_STYLES = ('sphere', 'crosshair', 'diamond', 'arrow', 'cone')


# ---------------------------------------------------------------------------
# Geometry generators
# ---------------------------------------------------------------------------

def _crosshair_geometry(size):
    """Three orthogonal thin rectangular prisms forming a 3D crosshair."""
    arm = size
    t = size * 0.1
    verts = []
    norms = []
    tris = []
    for axis in range(3):
        ext = [t, t, t]
        ext[axis] = arm
        hx, hy, hz = ext
        o = len(verts)
        v = [[-hx,-hy,-hz], [hx,-hy,-hz], [hx,hy,-hz], [-hx,hy,-hz],
             [-hx,-hy, hz], [hx,-hy, hz], [hx,hy, hz], [-hx,hy, hz]]
        verts.extend(v)
        for p in v:
            n = np.array(p, dtype=np.float32)
            mag = np.linalg.norm(n)
            norms.append(n / mag if mag > 0 else np.array([0,1,0], dtype=np.float32))
        tris.extend([
            [o+0,o+2,o+1], [o+0,o+3,o+2],
            [o+4,o+5,o+6], [o+4,o+6,o+7],
            [o+0,o+1,o+5], [o+0,o+5,o+4],
            [o+2,o+3,o+7], [o+2,o+7,o+6],
            [o+0,o+4,o+7], [o+0,o+7,o+3],
            [o+1,o+2,o+6], [o+1,o+6,o+5],
        ])
    return np.array(verts, np.float32), np.array(norms, np.float32), np.array(tris, np.int32)


def _diamond_geometry(size):
    """Octahedron (diamond) shape."""
    s = size
    verts = np.array([
        [ s, 0, 0], [-s, 0, 0],
        [ 0, s, 0], [ 0,-s, 0],
        [ 0, 0, s], [ 0, 0,-s],
    ], dtype=np.float32)
    norms = np.array([
        [1,0,0], [-1,0,0], [0,1,0], [0,-1,0], [0,0,1], [0,0,-1],
    ], dtype=np.float32)
    tris = np.array([
        [0,2,4], [2,1,4], [1,3,4], [3,0,4],
        [2,0,5], [1,2,5], [3,1,5], [0,3,5],
    ], dtype=np.int32)
    return verts, norms, tris


def _arrow_geometry(size):
    """3D cone pointer -- tip at origin, base extends in +Y.
    Tip sits on the surface; base points toward the camera."""
    length = size * 5
    base_r = size * 0.6
    n_seg = 16
    verts = [[0, 0, 0]]
    norms = [[0, -1, 0]]
    angles = np.linspace(0, 2 * np.pi, n_seg, endpoint=False)
    slope = base_r / length
    for a in angles:
        ca, sa = np.cos(a), np.sin(a)
        verts.append([base_r * ca, length, base_r * sa])
        nx, nz = ca, sa
        ny = -slope
        mag = np.sqrt(nx*nx + ny*ny + nz*nz)
        norms.append([nx/mag, ny/mag, nz/mag])
    bc = len(verts)
    verts.append([0, length, 0])
    norms.append([0, 1, 0])
    tris = []
    for i in range(n_seg):
        tris.append([0, 1 + (i + 1) % n_seg, 1 + i])
    for i in range(n_seg):
        tris.append([bc, 1 + i, 1 + (i + 1) % n_seg])
    return np.array(verts, np.float32), np.array(norms, np.float32), np.array(tris, np.int32)


def _pointer_geometry(size):
    """Classic mouse pointer cursor, extruded with side walls for
    real 3D depth.  Tip at origin so it sits on the surface;
    body extends in -Y (toward camera after rotation)."""
    s = size
    t = s * 0.15
    tip_y = s * 1.2
    pts = [
        [0, 0],
        [-s*0.40, -s*0.05 - tip_y],
        [-s*0.12,  s*0.15 - tip_y],
        [-s*0.12, -s*0.55 - tip_y],
        [ s*0.12, -s*0.55 - tip_y],
        [ s*0.12,  s*0.15 - tip_y],
        [ s*0.40, -s*0.05 - tip_y],
    ]
    faces_2d = [
        [0, 1, 2], [0, 2, 5], [0, 5, 6],
        [2, 3, 4], [2, 4, 5],
    ]
    verts = []
    norms = []
    tris = []
    n = len(pts)
    for p in pts:
        verts.append([p[0], p[1], t])
        norms.append([0, 0, 1])
    for f in faces_2d:
        tris.append(f)
    for p in pts:
        verts.append([p[0], p[1], -t])
        norms.append([0, 0, -1])
    for f in faces_2d:
        tris.append([n + f[0], n + f[2], n + f[1]])
    edges = [(0,1), (1,2), (2,3), (3,4), (4,5), (5,6), (6,0)]
    base = 2 * n
    for i, (a, b) in enumerate(edges):
        pa, pb = pts[a], pts[b]
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        nx, ny = dy, -dx
        mag = np.sqrt(nx*nx + ny*ny)
        if mag > 0:
            nx, ny = nx/mag, ny/mag
        vi = base + i * 4
        verts.extend([
            [pa[0], pa[1],  t],
            [pb[0], pb[1],  t],
            [pb[0], pb[1], -t],
            [pa[0], pa[1], -t],
        ])
        norms.extend([[nx, ny, 0]] * 4)
        tris.append([vi, vi+1, vi+2])
        tris.append([vi, vi+2, vi+3])
    return np.array(verts, np.float32), np.array(norms, np.float32), np.array(tris, np.int32)


# ---------------------------------------------------------------------------
# View rotation helpers (screen-fixed orientation)
# ---------------------------------------------------------------------------

def view_rotation(camera):
    """Return 3x3 rotation whose columns are camera right / up / -forward
    expressed in scene coordinates.  This is the TRANSPOSE of the view
    matrix rotation (view maps scene->camera; we need camera->scene).
    Screen-fixed overlays use this so they do not rotate with the molecule."""
    try:
        vp = camera.view(camera.position, 0)
        return vp.zero_translation().remove_scale().axes().T.copy()
    except Exception:
        return camera.position.zero_translation().remove_scale().axes().T.copy()


def arrow_view_rotation(R):
    """Modify view rotation so cone tip points straight into screen.
    Tip (Y=0) faces camera forward; base (Y=+length) faces the viewer.
    This keeps the cone body above any surface — only the tip touches."""
    from numpy.linalg import norm
    cam_fwd = -R[:, 2]
    # Y axis = tip-to-base = toward viewer (opposite of forward)
    y_ax = -cam_fwd
    x_ax = R[:, 0].copy()
    z_ax = np.cross(x_ax, y_ax)
    zl = norm(z_ax)
    if zl > 0:
        z_ax /= zl
    x_ax = np.cross(y_ax, z_ax)
    return np.column_stack([x_ax, y_ax, z_ax])


def pointer_view_rotation(R):
    """Tilt mouse arrow into screen like a classic 2D cursor.
    1) Tilt 60 deg into screen so the tip is prominent
    2) Roll 15 deg to show left side (classic cursor perspective).
    No horizontal lean — tip stays aligned horizontally."""
    import math
    from numpy.linalg import norm
    right = R[:, 0].copy()
    up = R[:, 1].copy()
    fwd = -R[:, 2]
    # Roll to show left side
    roll = math.radians(15)
    cr, sr = math.cos(roll), math.sin(roll)
    right2 = cr * right + sr * fwd
    fwd2 = -sr * right + cr * fwd
    tilt = math.radians(60)
    ct, st = math.cos(tilt), math.sin(tilt)
    y_ax = ct * up + st * fwd2
    x_ax = right2.copy()
    z_ax = np.cross(x_ax, y_ax)
    zl = norm(z_ax)
    if zl > 0:
        z_ax /= zl
    x_ax = np.cross(y_ax, z_ax)
    return np.column_stack([x_ax, y_ax, z_ax])


# ---------------------------------------------------------------------------
# Cursor3D
# ---------------------------------------------------------------------------

_DEFAULT_STYLE = 'sphere'
_DEFAULT_RADIUS = 0.4
# Default gradient: bright warm yellow center → deep orange edge
_DEFAULT_CENTER = np.array([255, 230, 100, 210], dtype=np.float32)
_DEFAULT_EDGE = np.array([210, 80, 0, 180], dtype=np.float32)


class Cursor3D:
    """3D cursor for autostereo displays.

    Renders a small shape in the scene at the depth of whatever is under
    the mouse.  Use ``xr3d cursor <style>`` to change style.
    """

    def __init__(self, session, style=_DEFAULT_STYLE, radius=_DEFAULT_RADIUS):
        self._session = session
        self._radius = radius
        self._style = style
        self._custom_color = None  # None = use default gradient
        self._last_pos = None
        self._last_pick_pos = None
        from chimerax.core.models import Surface
        self._model = m = Surface('3D Cursor', session)
        m.color = (255, 150, 0, 180)
        m.pickable = False
        m.display = False
        self._apply_style(style)
        session.models.add([m])
        # Enable key light shadows so cursor casts shadow on molecules
        self._prev_shadows = self._enable_shadows(session)

    @property
    def style(self):
        return self._style

    @property
    def last_pick_position(self):
        """Raw picked surface position, or None."""
        return self._last_pick_pos

    def set_style(self, style):
        """Change cursor style, preserving custom size and color."""
        self._style = style
        self._apply_style(style)

    def set_radius(self, radius):
        """Change cursor radius, preserved across style changes."""
        self._radius = radius
        self._apply_style(self._style)

    def set_color(self, color):
        """Set custom color with auto-contrast gradient.
        Preserves default alpha. color is a ChimeraX Color."""
        rgba = color.uint8x4()
        self._custom_color = rgba
        self._base_vc = self._make_gradient(self._base_va)
        self._model.vertex_colors = self._base_vc

    def reset_defaults(self):
        """Reset style, size, and color to defaults."""
        self._radius = _DEFAULT_RADIUS
        self._style = _DEFAULT_STYLE
        self._custom_color = None
        self._apply_style(self._style)

    def _apply_style(self, style):
        r = self._radius
        if style == 'sphere':
            from chimerax.surface import sphere_geometry2
            va, na, ta = sphere_geometry2(80)
            va = r * va
        elif style == 'crosshair':
            va, na, ta = _crosshair_geometry(r)
        elif style == 'diamond':
            va, na, ta = _diamond_geometry(r)
        elif style == 'arrow':
            va, na, ta = _pointer_geometry(r * 2.5)
        elif style == 'cone':
            va, na, ta = _arrow_geometry(r)
        else:
            return
        self._base_va = np.array(va, dtype=np.float64)
        self._base_na = np.array(na, dtype=np.float64)
        self._base_ta = np.array(ta, dtype=np.int32)
        self._base_vc = self._make_gradient(va)
        self._model.set_geometry(
            np.array(va, dtype=np.float32),
            np.array(na, dtype=np.float32),
            self._base_ta)
        self._model.vertex_colors = self._base_vc

    def _make_gradient(self, va):
        """Build gradient colors for current vertices.
        Uses default orange gradient or auto-contrast from custom color."""
        if self._custom_color is None:
            return self._default_gradient(va, self._style)
        return self._color_gradient(va, self._custom_color, self._style)

    @staticmethod
    def _default_gradient(va, style):
        """Default gradient: bright yellow center → deep orange edge."""
        return Cursor3D._compute_gradient(
            va, _DEFAULT_CENTER, _DEFAULT_EDGE, style)

    @staticmethod
    def _color_gradient(va, rgba, style):
        """Auto-contrast gradient from a custom color.
        Light colors get darker edges; dark colors get lighter edges.
        Very dark colors (like black) get strong bright edges so the
        shape reads as that color with visible 3D shading.
        Alpha is preserved from the default (210 center, 180 edge)."""
        r, g, b, _a = int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])
        # Perceived luminance (ITU-R BT.601)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum > 128:
            # Light color: darken edges
            center = np.array([r, g, b, 210], dtype=np.float32)
            edge = np.array([
                max(0, r - 80), max(0, g - 80), max(0, b - 80), 180
            ], dtype=np.float32)
        elif lum > 40:
            # Medium-dark: moderate lighten on edges
            center = np.array([r, g, b, 210], dtype=np.float32)
            edge = np.array([
                min(255, r + 110), min(255, g + 110), min(255, b + 110), 180
            ], dtype=np.float32)
        else:
            # Very dark (near-black): strong bright edges for contrast,
            # center stays dark so it reads as the chosen color
            center = np.array([r, g, b, 210], dtype=np.float32)
            edge = np.array([
                min(255, r + 180), min(255, g + 180), min(255, b + 180), 180
            ], dtype=np.float32)
        return Cursor3D._compute_gradient(va, center, edge, style)

    @staticmethod
    def _compute_gradient(va, c_center, c_edge, style):
        """Compute per-vertex gradient.  Uses Y-axis for cone (elongated
        along Y), radial from centroid for all other shapes."""
        n = len(va)
        if style == 'cone':
            # Gradient along Y axis (tip=0, base=max Y)
            y_vals = va[:, 1]
            y_min, y_max = y_vals.min(), y_vals.max()
            span = y_max - y_min
            t = (y_vals - y_min) / span if span > 1e-10 else np.zeros(n)
        else:
            # Radial from centroid
            centroid = va.mean(axis=0)
            dists = np.linalg.norm(va - centroid, axis=1)
            d_max = dists.max()
            t = dists / d_max if d_max > 1e-10 else np.zeros(n)
        colors = np.zeros((n, 4), dtype=np.uint8)
        for i in range(4):
            colors[:, i] = (c_center[i]
                            + t * (c_edge[i] - c_center[i])).astype(np.uint8)
        return colors

    # Per-style surface offset (Angstroms toward camera).
    # Positive = above surface, negative = into surface.
    _SURFACE_OFFSETS = {
        'sphere': 0.3,
        'crosshair': 0.3,
        'diamond': 0.3,
        'arrow': 0.15,   # tip almost touching
        'cone': -0.1,    # tip subtly dives in for precise selection
    }

    def update(self, x, y):
        view = self._session.main_view
        pick = view.picked_object(int(x), int(y))
        pos = None
        if (pick is not None and hasattr(pick, 'position')
                and pick.position is not None):
            self._last_pick_pos = pick.position.copy()
            pos = pick.position
            cam_origin = view.camera.position.origin()
            from numpy.linalg import norm
            to_cam = cam_origin - pos
            dist = norm(to_cam)
            if dist > 0:
                offset = self._SURFACE_OFFSETS.get(self._style, 0.3)
                pos = pos + offset * (to_cam / dist)
        else:
            self._last_pick_pos = None
            cam = view.camera
            origin, direction = cam.ray(int(x), int(y), view.window_size)
            if origin is not None:
                cofr = view.center_of_rotation
                from numpy.linalg import norm
                dist = norm(cofr - cam.position.origin())
                pos = origin + dist * 0.97 * direction

        if pos is not None:
            self._last_pos = pos
            self._place_geometry(pos, view.camera)
            self._model.display = True
        else:
            self._model.display = False

    def refresh(self):
        """Re-orient cursor at cached position without picking.
        Called each frame when mouse hasn't moved, to keep cursor
        screen-fixed as the camera moves (head tracking)."""
        if (self._last_pos is not None
                and self._model is not None and self._model.display):
            self._place_geometry(
                self._last_pos, self._session.main_view.camera)

    def _place_geometry(self, pos, camera):
        """Place cursor at pos with screen-fixed orientation.
        Rotation is baked into vertex positions via set_geometry();
        model.position handles translation only."""
        from chimerax.geometry import Place
        if self._style == 'sphere':
            va = self._base_va.astype(np.float32)
            na = self._base_na.astype(np.float32)
        else:
            R = view_rotation(camera)
            if self._style == 'cone':
                R = arrow_view_rotation(R)
            elif self._style == 'arrow':
                R = pointer_view_rotation(R)
            va = (R @ self._base_va.T).T.astype(np.float32)
            na = (R @ self._base_na.T).T.astype(np.float32)
        self._model.set_geometry(va, na, self._base_ta)
        if self._base_vc is not None:
            self._model.vertex_colors = self._base_vc
        self._model.position = Place(origin=pos)

    @property
    def deleted(self):
        return self._model is None or self._model.deleted

    @staticmethod
    def _enable_shadows(session):
        """Enable key light shadows and transparent shadow casting.
        Returns previous states so they can be restored."""
        prev = {'shadows': False, 'transparent': False}
        try:
            lp = session.main_view.lighting
            prev['shadows'] = lp.shadows
            if not lp.shadows:
                lp.shadows = True
            # Cursor is semi-transparent; without this it won't cast shadows
            mat = session.main_view.render.material
            prev['transparent'] = mat.transparent_cast_shadows
            if not mat.transparent_cast_shadows:
                mat.transparent_cast_shadows = True
            session.main_view.redraw_needed = True
        except Exception:
            pass
        return prev

    def _restore_shadows(self):
        """Restore shadow state to what it was before cursor was created."""
        try:
            prev = self._prev_shadows
            if not prev.get('shadows', False):
                self._session.main_view.lighting.shadows = False
            if not prev.get('transparent', False):
                self._session.main_view.render.material.transparent_cast_shadows = False
            self._session.main_view.redraw_needed = True
        except Exception:
            pass

    def hide(self):
        if self._model is not None:
            self._model.display = False

    def delete(self):
        if self._model is not None:
            self._model.display = False
            self._session.models.remove([self._model])
            self._model = None
            self._restore_shadows()


class SelectionRect3D:
    """3D selection rectangle for autostereo displays.
    Renders a semi-transparent quad at a given depth plane
    so the ctrl-drag selection area is visible in stereo."""

    def __init__(self, session):
        self._session = session
        from chimerax.core.models import Surface
        self._model = m = Surface('3D Selection', session)
        m.color = (100, 180, 255, 60)
        m.pickable = False
        m.display = False
        m.use_lighting = False
        session.models.add([m])

    def update(self, x0, y0, x1, y1, depth_point=None):
        """Update rectangle corners from graphics coordinates.
        depth_point: 3D point defining the plane depth (default: cofr)."""
        view = self._session.main_view
        cam = view.camera
        plane_point = (depth_point if depth_point is not None
                       else view.center_of_rotation)
        view_dir = -view_rotation(cam)[:, 2]
        ws = view.window_size
        corners_3d = []
        for cx, cy in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            origin, direction = cam.ray(int(cx), int(cy), ws)
            if origin is None:
                self._model.display = False
                return
            denom = np.dot(direction, view_dir)
            if abs(denom) < 1e-10:
                self._model.display = False
                return
            t = np.dot(plane_point - origin, view_dir) / denom
            corners_3d.append(origin + t * direction)
        verts = np.array(corners_3d, dtype=np.float32)
        norms = np.tile(view_dir.astype(np.float32), (4, 1))
        tris = np.array([
            [0, 1, 2], [0, 2, 3],
            [0, 2, 1], [0, 3, 2],
        ], dtype=np.int32)
        from chimerax.geometry import identity
        self._model.position = identity()
        self._model.set_geometry(verts, norms, tris)
        self._model.display = True

    def hide(self):
        if self._model is not None:
            self._model.display = False

    def delete(self):
        if self._model is not None:
            self._model.display = False
            self._session.models.remove([self._model])
            self._model = None
