# Toolshed description — paste this into the bundle's Description field

The Toolshed description is a **separate, hand-maintained field** on
<https://cxtoolshed.rbvi.ucsf.edu/apps/chimeraxxr3d>. It is *not* generated from
`bundle_info.xml` (whose `<Description>` is only two lines) and *not* from this repo's README.

That means it drifts. It already did: the v0.9 page documented `xr3d cursor shadows true`
while the README's command table omitted it entirely.

**Keep this file in sync with the README, and paste it into the Toolshed form on every release.**

---

Adds depth-correct 3D interaction to all OpenXR autostereo displays (Sony Spatial Reality,
Acer SpatialLabs, Samsung Odyssey 3D).

## Features

- **3D cursor** at correct stereo depth (5 styles: sphere, crosshair, diamond, arrow, cone)
- **Customizable** size, color with auto-contrast gradient
- **Saved preferences** — style, size, color and shadows persist across sessions
- **3D selection rectangle** for ctrl+drag region selection
- **Hover labels** for atoms, residues, and bonds
- **vrto3d view fitting** for Samsung Odyssey 3D

## Commands

| Command | Description |
|---|---|
| `xr3d cursor sphere` | Switch style (also: crosshair, diamond, arrow, cone) |
| `xr3d cursor size 0.6` | Adjust cursor size |
| `xr3d cursor color red` | Set custom color |
| `xr3d shadows true` | Enable cursor shadow casting (off by default) |
| `xr3d cursor shadows true` | Same, kept for compatibility |
| `xr3d cursor default` | Reset all to defaults and forget saved values |
| `xr3d on` / `xr3d off` | Enable/disable 3D cursor |

Command words, keywords and booleans truncate once unambiguous, so `xr3d sh on` works.

## Your cursor is remembered

Since v0.10, style, size, color and shadows are saved per user. Set the cursor you like once
and every later `xr on` restores it. `xr3d cursor default` resets to the shipped defaults and
clears the saved values.

Shadows ship **off**: shadow casting forces a shadow-map rebuild as the cursor moves, which is
noticeable on slower GPUs. It is a default, not a limit — `xr3d shadows true` once and it stays.
That command works with no XR session active, so it can go in a startup script.

## Requirements

- ChimeraX 1.11+ with OpenXR support
- An autostereo 3D display (Sony, Acer, or Samsung)
- For Samsung: vrto3d + SteamVR

## Links

- GitHub: https://github.com/andreply/ChimeraX-XR3D
