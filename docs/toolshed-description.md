# Toolshed description — paste the part below the rule into the bundle's Details field

The Toolshed description is a **separate, hand-maintained field** on
<https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxxr3d>. It is *not* generated from
`bundle_info.xml` (whose `<Description>` is only two lines) and *not* from this repo's README,
so it drifts. It already did: the v0.9 page documented `xr3d cursor shadows true` while the
README's command table omitted the keyword entirely.

**Keep this in sync with the README and paste it on every release.**

⚠ **The Toolshed's markdown renderer does not support tables.** The v0.9 page displayed the
Commands table as literal `|` pipes. Use lists, not tables.

Editor account for this bundle: `labyrinth_visa_7i@icloud.com` (Google sign-in; the Toolshed ties
edit rights to the account that made the original submission).

---

## ChimeraX-XR3D

Adds depth-correct 3D interaction to all OpenXR autostereo displays (Sony Spatial Reality, Acer SpatialLabs, Samsung Odyssey 3D).

### Features

- **3D cursor** at correct stereo depth (5 styles: sphere, crosshair, diamond, arrow, cone)
- **Customizable** size, color with auto-contrast gradient
- **Saved preferences** — style, size, color and shadows persist across sessions
- **3D selection rectangle** for ctrl+drag region selection
- **Hover labels** for atoms, residues, and bonds
- **Depth-correct 3D labels** — labels stop drawing through the geometry in front of them
- **vrto3d view fitting** for Samsung Odyssey 3D

### Commands

- `xr3d on` / `xr3d off` — enable or disable the 3D cursor
- `xr3d cursor sphere` — switch style (also: crosshair, diamond, arrow, cone)
- `xr3d cursor size 0.6` — adjust cursor size
- `xr3d cursor color red` — set a custom color
- `xr3d shadows true` — enable cursor shadow casting (off by default)
- `xr3d cursor default` — reset everything to defaults and forget saved values
- `xr3d labels` — report the current label settings
- `xr3d labels depth false` — leave labels alone, as stock ChimeraX draws them
- `xr3d labels plate 30 lift 2` — adjust the label backplate and lift

### Depth-correct labels

ChimeraX draws 3D labels on top of everything, with depth testing off. On a flat screen that is a readability win, since a label can never be hidden. In stereo it is the opposite: the label keeps the parallax of its anchor point, so your eyes converge on a position inside the molecule while the label is painted over what is in front of it. The two depth cues disagree, and it is tiring within seconds.

While an XR session is running, labels become ordinary objects in the scene: depth tested, hidden when something is in front of them, and lifted slightly toward you so a label is not eaten by the side chain it names. They also get a dark backplate, because once a label can be occluded, white text over a white ribbon is hard to read.

Molecular surfaces get special treatment, because a surface stands several Ångström outside the residue it covers and would bury every label. When an **opaque** surface is shown, each label moves out onto its own surface patch instead, so it names the patch you are looking at. Labels with nowhere sensible to go are suppressed rather than misplaced: patches too small to name, residues in grooves overhung by their neighbours, buried residues, and distance labels, which belong to no residue. When the surface is **transparent** the labels stay where they are and shine through it, exactly as the cartoon and sticks do.

Everything is restored when the XR session ends, so your flat-screen labels are untouched. All values are saved, and `xr3d labels` works with no XR session running.

Commands, keywords and booleans can be truncated once unambiguous, so `xr3d sh on` works.

`xr3d cursor shadows true` is still accepted, for compatibility with existing scripts.

### Your cursor is remembered

Since v0.10, style, size, color and shadows are **saved per user**. Set the cursor you like once and every later `xr on` restores it — no startup script needed.

```
xr3d cursor cone size 0.6 color cornflowerblue
xr3d shadows true
```

`xr3d cursor default` resets to the shipped defaults and clears the saved values.

### Shadows

The cursor can cast a shadow onto the molecule, which makes its depth much easier to read.

It ships **off**, because shadow casting forces a shadow-map rebuild as the cursor moves and that is noticeable on slower GPUs. It is a default, not a limit — turn it on once and it stays on. `xr3d shadows` also works with no XR session active, so it can go in a startup script or be set before the display is connected.

### Requirements

- ChimeraX 1.11+ with OpenXR support
- An autostereo 3D display (Sony, Acer, or Samsung)
- For Samsung: [vrto3d](https://github.com/oneup03/VRto3D) + SteamVR

### Links

- GitHub: https://github.com/andreply/ChimeraX-XR3D
