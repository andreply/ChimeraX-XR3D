# vim: set expandtab shiftwidth=4 softtabstop=4:

"""Depth-correct 3D labels while an XR display is active.

ChimeraX object labels ship with ``on_top = True`` (``label/label3d.py``), which
routes them into a final draw pass that turns the depth test off outright
(``graphics/drawing.py``, ``draw_on_top``).  On a flat screen that is a
readability win: a label can never be hidden.  In stereo it is the opposite.
The label keeps the parallax of its anchor point, so the eyes converge on a
position *inside* the molecule while the label is painted over everything in
front of it.  The two depth cues contradict each other and it is tiring within
seconds.  That is the bug this module exists to fix.

Making labels depth tested is one ``label`` option, but doing only that leaves
three new problems, each of which needed measuring rather than guessing.  The
rules below are the settled result; the numbers are from 1l2y on the Odyssey.

**A label is eaten by its own residue.**  Residue labels sit at the residue
centroid, so depth testing alone buries them in the side chain they name.  They
are lifted a constant 1.5 A toward the viewer.  Deriving that lift per label
from the visible atoms was built and rejected: it is the *smallest* correct lift
but it changes as the scene rotates, and a label that swims in depth is worse to
look at than one sitting slightly too far out.  Constant beats minimal.

**A molecular surface buries everything.**  An SES surface stands 3.1 to 8.7 A
out from the same anchor, so inside a surface the flat lift is hopeless.  When an
*opaque* surface is displayed, each label instead moves onto its own surface
patch: out along the local radial direction, far enough to clear every surface
vertex along that ray, plus a margin.  Three details were each established by
measurement:

* The direction is *not* the patch's mean normal.  For a patch whose normals
  cancel that points nowhere useful (TRP 6: coherence 0.37, 70 degrees off
  outward, label flung 10 A sideways).  A radial direction from the centroid of
  nearby surface left 0 of 20 targets buried, against 1 for the mean normal and
  7 for anchoring on the patch's outermost vertex.
* The ray must clear the *whole* surface, not the residue's own patch.  Clearing
  only its own patch left TRP 6 4.9 A inside the surface, because a residue in a
  groove is overhung by its neighbours.
* Splitting a residue's patch into connected pieces and taking the largest does
  not work: ``vertex_to_atom_map`` assigns SES vertices to nearest atoms, so a
  residue's vertex set is speckled and fragments into 10 to 22 pieces for
  mesh-indexing reasons rather than shape.

**Some labels have nowhere to go.**  Under an opaque surface a label is
suppressed rather than misplaced when its patch is too small to name, when it
would need more than ``max_travel`` to escape a groove, or when there is no patch
at all (a buried residue, or a distance label, which belongs to no residue).

**The plate is not a free choice.**  Labels get a dark plate, because once a
label can be occluded, white text over a white ribbon is hard to read.  Its
opacity is managed, not chosen: ChimeraX only lets a label show through a
transparent surface when *every* label in that model has a fully opaque
background (documented on the ``label`` page, and enforced by
``ObjectLabels._all_labels_opaque``).  So while a transparent surface is
displayed the plate is forced opaque, and elsewhere it relaxes to
``plate_percent``.  Labels with no plate are given one, which is not cosmetic: a
single plateless label drags its whole model into the transparent pass and a
transparent surface then erases every label in it.

Everything is restored when the XR session ends.  Transparency changes are
polled rather than triggered, because changing a surface's transparency is a
colour change and fires none of the display or shape triggers.
"""

import numpy

#: Shipped defaults.  Settable and saved via `xr3d labels`.
DEFAULT_DEPTH = True
DEFAULT_LIFT = 1.5        # A toward the viewer, where no surface is in the way
DEFAULT_PLATE = 45        # percent, relaxed value; forced to 100 when required
DEFAULT_PATCH_OFFSET = 1.5   # A of air outside the surface patch
DEFAULT_MIN_AREA = 20.0      # A^2; a smaller patch carries no label
DEFAULT_MAX_TRAVEL = 6.0     # A; further than this means "no usable patch"

#: Not exposed: geometry constants with no reason to be tuned per session.
_RAY_RADIUS = 2.0      # A, thickness of the ray used to find blocking surface
_LOCAL_RADIUS = 12.0   # A, neighbourhood defining which way is "out" locally
_NEAR_LIMIT = 25.0     # A, beyond which surface cannot block a label

_SAVED = '_xr3d_labels_original'

_state = {
    'lift': DEFAULT_LIFT,
    'plate': DEFAULT_PLATE,
    'patch_offset': DEFAULT_PATCH_OFFSET,
    'min_area': DEFAULT_MIN_AREA,
    'max_travel': DEFAULT_MAX_TRAVEL,
    'targets': None,        # residue/object -> scene-coordinate target point
    'blocked': False,       # is an opaque surface drawn at all
    'fingerprint': None,
    'session': None,
    'handlers': [],
    'degraded': False,      # patching failed; native-only behaviour in use
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def enable(session, **kw):
    """Take labels over.  Safe to call again to change the numbers."""
    for key in ('lift', 'plate', 'patch_offset', 'min_area', 'max_travel'):
        if kw.get(key) is not None:
            _state[key] = kw[key]
    _state['session'] = session
    # is_enabled(), not _installed(): if the core patch failed we are still
    # active (handlers plus depth testing), and re-running _install would
    # double-patch drawings_for_each_pass and then "restore" our own wrapper.
    if not is_enabled():
        _install(session)
    _invalidate()
    _sync_plates(session)
    _refresh(session)


def disable(session):
    """Give labels back to ChimeraX exactly as they were."""
    if _installed() or _state['handlers']:
        _uninstall(session)
        _refresh(session)


def is_enabled():
    return _installed() or bool(_state['handlers'])


def describe():
    if not is_enabled():
        return 'labels: stock ChimeraX (always in front)'
    extra = ' (reduced: core internals changed)' if _state['degraded'] else ''
    return ('labels: depth tested, lift %.2f A, plate %d%%, patch offset %.2f A, '
            'min patch %.0f A^2%s'
            % (_state['lift'], _state['plate'], _state['patch_offset'],
               _state['min_area'], extra))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _opaque(surface):
    """Does this surface draw anything the eye cannot see through?"""
    try:
        any_opaque, any_transparent = surface._transparency()
        return any_opaque
    except Exception:
        try:
            return not surface.showing_transparent()
        except Exception:
            return True


def _drawing_surfaces(session):
    """Displayed molecular surfaces that actually draw something.

    ``surface hidePatches`` masks triangles instead of undisplaying the model, so
    a surface can report display=True, opaque, 31926 triangles and 0 of them
    shown.  ``show_atoms`` is the only honest answer.
    """
    from chimerax.atomic import MolecularSurface
    out = []
    for s in session.models.list(type=MolecularSurface):
        if not s.visible:
            continue
        shown = s.show_atoms
        if shown is None or len(shown) == 0:
            continue
        out.append((s, shown))
    return out


def _compute_targets(session):
    """Where each label goes, and whether an opaque surface is in the way."""
    targets = {}
    blocked = False
    offset = _state['patch_offset']
    min_area = _state['min_area']
    max_travel = _state['max_travel']

    for s, shown in _drawing_surfaces(session):
        if not _opaque(s):
            continue          # transparent: an opaque label shines through it
        v2a = s.vertex_to_atom_map()
        if v2a is None:
            continue
        blocked = True
        atoms = s.atoms
        # Scene coordinates, so surface and labels need not share a frame.
        verts = s.scene_position.transform_points(s.vertices)
        shown_residues = set(shown.unique_residues)

        uniq = atoms.unique_residues
        index = {r: i for i, r in enumerate(uniq)}
        per_vertex = numpy.array([index[r] for r in atoms.residues])[v2a]
        n = len(uniq)
        counts = numpy.bincount(per_vertex, minlength=n).astype(float)
        vsum = numpy.zeros((n, 3))
        numpy.add.at(vsum, per_vertex, verts)
        usable = counts > 0
        centres = numpy.zeros((n, 3))
        centres[usable] = vsum[usable] / counts[usable, None]

        area = None
        if min_area > 0:
            tri = s.triangles
            mask = s.triangle_mask
            if mask is not None:
                tri = tri[mask]
            v0, v1, v2 = verts[tri[:, 0]], verts[tri[:, 1]], verts[tri[:, 2]]
            tri_area = 0.5 * numpy.linalg.norm(
                numpy.cross(v1 - v0, v2 - v0), axis=1)
            area = numpy.zeros(n)
            numpy.add.at(area, per_vertex[tri[:, 0]], tri_area)

        for i, r in enumerate(uniq):
            if not usable[i] or r not in shown_residues:
                continue
            if area is not None and area[i] < min_area:
                continue
            point = _patch_target(verts, centres[i], offset, max_travel)
            if point is not None:
                targets[r] = point

    return targets, blocked


def _patch_target(verts, centre, offset, max_travel):
    """A point just outside the surface, straight out from this patch."""
    rel = verts - centre
    dist = numpy.linalg.norm(rel, axis=1)

    near = dist < _LOCAL_RADIUS
    local = verts[near].mean(axis=0) if near.any() else verts.mean(axis=0)
    direction = centre - local
    length = numpy.linalg.norm(direction)
    if length < 1e-6:
        return None
    direction = direction / length

    sel = dist < _NEAR_LIMIT
    rel_near = rel[sel]
    proj = rel_near.dot(direction)
    perp = numpy.linalg.norm(rel_near - proj[:, None] * direction, axis=1)
    blocking = (proj > 0) & (perp < _RAY_RADIUS)
    travel = (float(proj[blocking].max()) if blocking.any() else 0.0) + offset
    if travel > max_travel:
        return None     # overhung by neighbours: no place both on it and outside
    return centre + direction * travel


# ---------------------------------------------------------------------------
# Plates
# ---------------------------------------------------------------------------

def _sync_plates(session):
    """Give every label a plate, at the opacity the scene requires."""
    from chimerax.label.label3d import ObjectLabels
    forced = any(not _opaque(s) for s, _ in _drawing_surfaces(session))
    want = 255 if forced else int(round(255 * _state['plate'] / 100))
    for m in session.models.list(type=ObjectLabels):
        changed = False
        for label in m.labels():
            bg = label.background
            if bg is None:
                label.background = (0, 0, 0, want)
                changed = True
            elif int(bg[3]) != want:
                label.background = (bg[0], bg[1], bg[2], want)
                changed = True
        if changed:
            m.update_labels()
    return want


# ---------------------------------------------------------------------------
# Patching
# ---------------------------------------------------------------------------

def _installed():
    try:
        from chimerax.label.label3d import ObjectLabel
    except ImportError:
        return False
    return hasattr(ObjectLabel, _SAVED)


def _invalidate():
    _state['targets'] = None


def _ensure_targets():
    if _state['targets'] is None:
        session = _state['session']
        _state['targets'], _state['blocked'] = _compute_targets(session)
    return _state['targets'], _state['blocked']


def _install(session):
    """Patch core, and fall back to native-only behaviour if that fails.

    The patched methods are internals, so a future ChimeraX refactor of
    label3d.py can break them.  If that happens the user still gets depth
    testing and plates, which is most of the benefit and needs no patching.
    """
    from chimerax.label.label3d import ObjectLabel, ObjectLabels
    from chimerax.label import label3d as _l3

    try:
        original_rect = ObjectLabel._label_rectangle
        visibles = {}

        def rectangle(self, scene_position, camera_position, _orig=original_rect):
            va = _orig(self, scene_position, camera_position)
            if va is None:
                return va
            targets, _ = _ensure_targets()
            point = targets.get(self.object)
            if point is not None:
                anchor = self.location(scene_position)
                if anchor is not None:
                    shift = point - (scene_position * anchor)
                    return va + scene_position.inverse().transform_vector(shift)
            return va + camera_position.transform_vector((0, 0, _state['lift']))

        def visible(self):
            saved = getattr(ObjectLabel, _SAVED, None)
            originals = saved['visible'] if saved else {}
            for cls in type(self).__mro__:
                if cls in originals:
                    if not originals[cls](self):
                        return False
                    break
            targets, blocked = _ensure_targets()
            if self.object in targets:
                return True
            # An opaque surface is drawn but this label has no place outside it,
            # so showing it would mean a label cut in half by the surface.
            return not blocked

        # visible() is overridden per label class, so patching only the base
        # would silently do nothing.  Wrap every class that defines its own.
        for cls in vars(_l3).values():
            if (isinstance(cls, type) and issubclass(cls, ObjectLabel)
                    and 'visible' in vars(cls)):
                visibles[cls] = vars(cls)['visible']
                cls.visible = visible

        ObjectLabel._label_rectangle = rectangle
        setattr(ObjectLabel, _SAVED,
                {'rectangle': original_rect, 'visible': visibles})
        _state['degraded'] = False
    except Exception as e:
        _state['degraded'] = True
        session.logger.warning(
            'ChimeraX-XR3D: could not take over label placement (%s). '
            'Labels are depth tested but will not move onto surface patches.'
            % e)

    # Labels stop drawing on top.  Inherited from Drawing, so remember whether
    # ObjectLabels owned one before we shadowed it.  Guarded so a repeated
    # install cannot capture our own wrapper as "the original".
    if 'passes' in _state:
        _add_handlers(session)
        return
    passes = ObjectLabels.drawings_for_each_pass
    owned = 'drawings_for_each_pass' in ObjectLabels.__dict__

    def depth_tested(self, pass_drawings, _orig=passes):
        on_top = self.on_top
        self.on_top = False
        try:
            return _orig(self, pass_drawings)
        finally:
            self.on_top = on_top

    ObjectLabels.drawings_for_each_pass = depth_tested
    _state['passes'] = (passes, owned)

    _add_handlers(session)


def _add_handlers(session):
    from chimerax.atomic import get_triggers

    def changed(*args):
        _invalidate()
        _sync_plates(session)
        _refresh(session)

    _state['handlers'].append(
        ('atomic', get_triggers().add_handler('changes', changed)))
    for name in ('model display changed', 'shape changed'):
        try:
            _state['handlers'].append(
                ('session', session.triggers.add_handler(name, changed)))
        except Exception:
            pass

    # Transparency is a colour change and fires none of the above, so the
    # surface state is polled.  The poll is cheap and the expensive recompute
    # only runs when the summary actually differs.
    _state['fingerprint'] = _fingerprint(session)

    def poll(*args):
        fp = _fingerprint(session)
        if fp != _state['fingerprint']:
            _state['fingerprint'] = fp
            changed()

    _state['handlers'].append(
        ('session', session.triggers.add_handler('graphics update', poll)))


def _fingerprint(session):
    return tuple((id(s), bool(_opaque(s)), len(shown))
                 for s, shown in _drawing_surfaces(session))


def _uninstall(session):
    from chimerax.label.label3d import ObjectLabel, ObjectLabels
    from chimerax.atomic import get_triggers

    saved = getattr(ObjectLabel, _SAVED, None)
    if saved is not None:
        ObjectLabel._label_rectangle = saved['rectangle']
        for cls, fn in saved.get('visible', {}).items():
            cls.visible = fn
        delattr(ObjectLabel, _SAVED)

    passes = _state.pop('passes', None)
    if passes is not None:
        original, owned = passes
        if owned:
            ObjectLabels.drawings_for_each_pass = original
        else:
            try:
                del ObjectLabels.drawings_for_each_pass
            except AttributeError:
                pass

    while _state['handlers']:
        kind, handler = _state['handlers'].pop()
        try:
            if kind == 'atomic':
                get_triggers().remove_handler(handler)
            else:
                session.triggers.remove_handler(handler)
        except Exception:
            pass
    _invalidate()


def _refresh(session):
    """Force labels to rebuild: geometry, visibility and texture all change."""
    try:
        from chimerax.label.label3d import ObjectLabels
    except ImportError:
        return
    for m in session.models.list(type=ObjectLabels):
        m.update_labels()                 # texture, for the plate
        m._positions_need_update = True   # geometry, for the lift
        m._visibility_needs_update = True  # which labels are drawn at all
        m.redraw_needed()
