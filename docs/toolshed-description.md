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
- **Depth-correct 3D labels** — labels stop drawing through the geometry in front of them
- **Saved preferences** — cursor and label settings persist across sessions
- **3D selection rectangle** for ctrl+drag region selection
- **Hover labels** for atoms, residues, and bonds
- **vrto3d view fitting** for Samsung Odyssey 3D

### Commands

- `xr3d on` / `xr3d off` — enable or disable the 3D cursor
- `xr3d cursor sphere` — switch style (also: crosshair, diamond, arrow, cone)
- `xr3d cursor size 0.6` — adjust cursor size
- `xr3d cursor color red` — set a custom color
- `xr3d shadows true` — enable cursor shadow casting (off by default)
- `xr3d cursor default` — reset everything to defaults and forget saved values
- `xr3d labels` — report the current label settings
- `xr3d labels depth false` — leave labels exactly as ChimeraX draws them
- `xr3d labels lift 2 plate 30` — tune label placement (also: `patchOffset`, `minArea`, `maxTravel`)

Commands, keywords and booleans can be truncated once unambiguous, so `xr3d sh on` works.

`xr3d cursor shadows true` is still accepted, for compatibility with existing scripts.

### Depth-correct labels

ChimeraX draws 3D labels on top of everything, with depth testing off. On a flat screen that is a readability win. In stereo it fights the depth cue: your eyes converge on the label's anchor inside the molecule while the label is painted over whatever is in front of it, and it is tiring within seconds.

Since v0.12, while XR is running, labels become ordinary objects in the scene — depth tested, lifted slightly toward you so a label is not eaten by the side chain it names, and given a dark backplate to stay readable.

Molecular surfaces are handled too, since a surface stands several Ångström outside the residue it covers and would otherwise bury every label:

- over an **opaque** surface, each label moves out onto its own surface patch, and labels with nowhere sensible to go are hidden rather than misplaced
- over a **transparent** surface, labels stay where they are and shine through it, exactly as the cartoon and sticks do

Everything is restored on `xr off`, so your flat-screen labels are untouched. Tuning is optional: `lift`, `plate`, `patchOffset`, `minArea` and `maxTravel` all ship with working defaults.

### Your cursor is remembered

Since v0.10, style, size, color and shadows are **saved per user**. Set the cursor you like once and every later `xr on` restores it — no startup script needed.

    xr3d cursor cone size 0.6 color cornflowerblue
    xr3d shadows true

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
