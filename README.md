# Chromatic Sorter

Rearranges the icons on your Windows desktop by colour or by category. It reads every desktop icon, works out its dominant colour, and moves the icons into a layout: a rainbow grid, rainbow pillars, a colour wheel around the screen edges, or category corners.

Every layout is previewed in the terminal first, and every change is backed up so you can undo it.

## Requirements

- Windows 10 or 11
- 64-bit Python 3.10 or newer (Explorer is 64-bit, so a 32-bit Python won't work)
- `pywin32` and `Pillow`

```
py -m pip install pywin32 Pillow
```

## Before you start

Right-click the desktop, open **View**, and make sure **Auto arrange icons** is **off**. With it on, Explorer puts the icons straight back.

**Align icons to grid** can stay on; the script places icons on Explorer's own grid.

## Quick start

```
py chromatic_sorter.py rainbow            # preview only, nothing moves
py chromatic_sorter.py rainbow --apply    # move the icons (asks for confirmation)
py chromatic_sorter.py restore            # undo the last change
```

Without `--apply`, the script only prints a colour map of the planned layout, one block per icon, so you can see the result before committing to it.

## Layouts

| Command | What it does |
|---|---|
| `rainbow` | All icons sorted by hue, left to right, top to bottom. |
| `pillars` | The rainbow split into vertical pillars. Use `-n` for 2–6 pillars (default 2). |
| `circle` | A colour wheel around the screen edges, clockwise from the top-left corner. |
| `borders` | Icons around the outer edge of the screen with the centre left empty, filled ring by ring. |
| `corners` | Icons grouped by category into the four corners, sorted by colour within each group. |

### Pillars

Pillars are shared between the left and right edges, and an odd number adds one in the middle:

| `-n` | Arrangement |
|---|---|
| 2 | left, right |
| 3 | left, middle, right |
| 4 | 2 left, 2 right |
| 5 | 2 left, middle, 2 right |
| 6 | 3 left, 3 right |

The colours run from the leftmost pillar to the rightmost. A pillar gets wider when there are too many icons for a single column.

```
py chromatic_sorter.py pillars -n 4 --apply
```

### Circle and borders

Both keep the centre of the screen clear. If there are more icons than edge cells, the frame gets thicker.

- `circle` places icons by angle around the screen centre, so the colours flow smoothly all the way round and icons of the same colour sit next to each other from the outer ring to the inner one.
- `borders` fills the whole outer ring first, then the next ring in.

### Corners

| Corner | Category | Matched by (examples) |
|---|---|---|
| Top-left | Productivity | Office, Adobe, Obsidian, Blender, Audacity |
| Top-right | Development | VS Code, JetBrains IDEs, Unity, Docker, Git |
| Bottom-left | Utilities | Browsers, Discord, Spotify, VPNs, Recycle Bin |
| Bottom-right | Gaming | Steam, Epic, Riot, GOG, Battle.net, Ubisoft |
| Centre | Other | Anything that matches none of the above |

Categories come from keywords found in the icon's name, file path and shortcut target. To teach it about your own apps, create a JSON file:

```json
{
  "Gaming": ["factorio", "rimworld"],
  "Development": ["sublime"]
}
```

and pass it in:

```
py chromatic_sorter.py corners --categories my_categories.json
```

Your keywords are added to the built-in ones. Only the four category names above are accepted.

## Backups and undo

Every `--apply` first saves the current icon positions to `%LOCALAPPDATA%\ChromaticSorter\backup-<date>-<time>.json`.

```
py chromatic_sorter.py restore                      # restore the newest backup
py chromatic_sorter.py restore --file <backup.json> # restore a specific one
py chromatic_sorter.py backup                       # save the current layout without changing anything
```

Backups match icons by name. Icons added since the backup are left where they are.

## Options

| Option | Meaning |
|---|---|
| `--apply` | Actually move the icons. Without it, layouts are only previewed. |
| `-y`, `--yes` | Skip the confirmation prompt. |
| `-n N`, `--pillars N` | Number of pillars for `pillars` (2–6). |
| `-v`, `--verbose` | List every icon with its grid cell, category and hue. |
| `--categories FILE` | Extra category keywords (JSON). |
| `--file FILE` | Backup to use with `restore`. |
| `--no-color` | Plain-text preview: hue initials (R, O, Y, G, C, B, P, M) instead of coloured blocks, with N for grey/black/white icons. |
| `--timeout MS` | How long to wait for Explorer per message (default 2000). |

## How it works

- **Reading the desktop.** The desktop is a list-view control owned by `explorer.exe`. Messages that pass a pointer to that control are handled inside Explorer, so the pointer has to point into Explorer's memory. The script allocates a buffer inside Explorer (`VirtualAllocEx`), sends the message, and copies the result back (`ReadProcessMemory`) to get each icon's name and position.
- **Finding the icons.** Names are matched against the desktop's shell folder, which also covers the Public desktop and virtual items such as the Recycle Bin. The icon image is taken from the same system image list Explorer draws from, so custom shortcut icons are respected.
- **Measuring colour.** Each icon is rendered at 48×48 and converted to HSV. Only reasonably saturated, visible pixels count towards the hue. Mostly black, white or grey icons are marked neutral and placed after the colours, light to dark.
- **Moving icons.** Icons are moved in an order where each target cell is already free, because Explorer bumps an icon dropped onto an occupied cell. If the move fails partway, icons that were already moved are put back.

## Troubleshooting

- **"Auto arrange icons is enabled"**: turn it off under desktop right-click > View.
- **"The desktop grid has N cells for M icons"**: too many icons for the screen. Switch to smaller icons (desktop right-click > View > Small icons) or remove a few.
- **"pillars ... do not fit"**: use fewer pillars.
- **"Python and Explorer have different bitness"**: install 64-bit Python.
- **An icon lands in the wrong category**: add a keyword with `--categories`.

## Limitations

- Only the primary monitor is used.
- Explorer saves icon positions itself, usually when you sign out or it restarts. Until then, if Explorer crashes the new layout may be lost; run the command again or use `restore`.
