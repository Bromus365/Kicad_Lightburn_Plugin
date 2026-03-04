## Plot via KiCad (LightBurn) – KiCad → LightBurn helper plugin

This repository contains a KiCad 9 action plugin that exports a PCB for laser
processing in **LightBurn**, using **KiCad's plotter** plus **Inkscape** to
prepare clean SVG geometry.

### Features

- Plots these layers from the currently open board:
  - Top copper (`F.Cu`)
  - Bottom copper (`B.Cu`)
  - Board outline (`Edge.Cuts`)
  - Top / bottom silkscreen (`F.SilkS`, `B.SilkS`)
  - Drills (vias + through‑hole pads)
- Runs **Inkscape** on the copper SVGs to:
  - Convert strokes to paths
  - Convert objects to paths
  - Ungroup
  - Union shapes
- Produces a single, combined SVG with:
  - Top copper, bottom copper, edge cuts, drills, and silkscreen
  - All **pre‑aligned** and
  - Color‑separated so each logical layer becomes a separate LightBurn layer.
- Automatically launches **LightBurn** with the combined SVG.

### Requirements

- **KiCad 9.x** (plugin uses the pcbnew Python API shipped with KiCad 9)
- **LightBurn** installed, e.g.
  - `C:\Program Files\LightBurn\LightBurn.exe` (default)
  - or LightBurn available on your `PATH`
- **Inkscape** with CLI support, e.g.
  - `C:\Program Files\Inkscape\bin\inkscape.exe` (default)
  - or `inkscape` available on your `PATH`

If LightBurn or Inkscape are installed in non‑default locations, you can edit
these constants in `LB_kicad_plugin/plugins/lb_plot_lightburn_kicad.py`:

```python
DEFAULT_LIGHTBURN_PATH = r"C:\Program Files\LightBurn\LightBurn.exe"
DEFAULT_INKSCAPE_PATH = r"C:\Program Files\Inkscape\bin\inkscape.exe"
```

### Installation (via KiCad Plugin & Content Manager)

1. **Create a ZIP package**

   From the repository root (where this `README.md` lives), the plugin folder is
   `LB_kicad_plugin/`. Package it like this:

   - Select `LB_kicad_plugin/metadata.json`
   - Select `LB_kicad_plugin/plugins/`
   - Select `LB_kicad_plugin/resources/`
   - Zip those three items so the ZIP root looks like:

   ```text
   metadata.json
   plugins/
   resources/
   ```

2. **Install in KiCad**

   - Open **KiCad 9 → Plugin and Content Manager**
   - Click **Install from file…**
   - Choose the ZIP you just created
   - Confirm install and restart the **PCB Editor** if needed

3. **Verify plugin appears**

   In the PCB Editor you should see:

   - Menu entry: `Tools → External Plugins → Plot via KiCad (LightBurn)`
   - Toolbar button with the laser‑eye icon

### Usage

1. Open your board in **KiCad PCB Editor** and **save** it.
2. In PCB Editor, run:

   - `Tools → External Plugins → Plot via KiCad (LightBurn)`
   - Or click the toolbar button with the laser‑eye icon.

3. The plugin will:

   - Plot:
     - `F.Cu` → `<board>_kicad_top.svg`
     - `B.Cu` → `<board>_kicad_bottom.svg`
     - `Edge.Cuts` → `<board>_kicad_edge.svg`
     - `F.SilkS` → `<board>_kicad_fsilk.svg`
     - `B.SilkS` → `<board>_kicad_bsilk.svg`
   - Generate drills:
     - `<board>_kicad_drills.svg` (vias + through‑hole pads as circles)
   - Run Inkscape on the top and bottom copper SVGs to convert strokes to paths
     and union shapes, producing:
     - `<board>_kicad_top_lb.svg`
     - `<board>_kicad_bottom_lb.svg`
   - Build a combined SVG:
     - `<board>_kicad_all_lb.svg`
     - Contains **all** layers (top/bottom copper, outline, drills, silkscreen)
     - All pre‑aligned and color‑separated into SVG groups.
   - Launch LightBurn with `<board>_kicad_all_lb.svg`.

### LightBurn layer mapping

In the combined SVG (`*_kicad_all_lb.svg`), the plugin enforces these colors:

- `copper_top`   → red     `#ff0000`
- `copper_bottom` → green  `#00aa00`
- `edge_cuts`    → black   `#000000`
- `drills`       → blue    `#0000ff`
- `silk_top`     → yellow  `#ffff00`
- `silk_bottom`  → magenta `#ff00ff`

LightBurn automatically maps each distinct color to its own layer, so you can:

- Enable/disable:
  - Top copper, bottom copper
  - Drills
  - Outline
  - Silkscreen
- Assign different power/speed/pass settings per color.

Typical workflow:

1. Run the plugin in KiCad to open the combined SVG in LightBurn.
2. In LightBurn, verify each color is on its own layer (C00–Cxx).
3. Configure layers:
   - **Top copper (red)**: set to **Fill** (no Line). This avoids LightBurn trying to cut along tiny internal boundaries where planes or traces meet; the laser will remove/mark copper by area instead of following every outline.
   - **Bottom copper (green)**: also **Fill** only (no Line), on the flipped board.
   - Drills (blue): full‑depth cuts for holes.
   - Edge cuts (black): full‑depth cut of the board perimeter (run last).
   - Silkscreen (yellow/magenta): engraving for markings.

### Development / GitHub

If you want to put this on GitHub:

```bash
git init
git add LB_kicad_plugin README.md
git commit -m "Add Plot via KiCad (LightBurn) plugin"
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

You may also want a `.gitignore` that at least ignores any local `venv/` or
build artifacts.

