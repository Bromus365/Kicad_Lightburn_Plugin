#!/usr/bin/env python3
"""
Alternate KiCad → LightBurn export using KiCad's internal plotter plus Inkscape.

This plugin:
  - Plots F.Cu, B.Cu, Edge.Cuts, and silkscreen to SVG files using KiCad's plotter.
  - Generates a drills SVG from vias and through-hole pads.
  - Uses Inkscape CLI on the F.Cu and B.Cu SVGs to:
      select-all → object-to-path → stroke-to-path → ungroup → union
    and writes *_top_lb.svg and *_bottom_lb.svg files.
  - Creates a combined SVG that contains all layers (top/bottom copper, drills,
    edge cuts, silkscreen) pre-aligned and color-separated for LightBurn.
  - Opens LightBurn with the combined SVG.
"""

import os
import subprocess
from shutil import which
import xml.etree.ElementTree as ET
import copy

import pcbnew
import wx


# LightBurn locator (previously in lb_open_lightburn.py, now local here)
DEFAULT_LIGHTBURN_PATH = r"C:\Program Files\LightBurn\LightBurn.exe"


def _find_lightburn_exe():
    """Try to locate the LightBurn executable."""
    if os.path.isfile(DEFAULT_LIGHTBURN_PATH):
        return DEFAULT_LIGHTBURN_PATH
    exe = which("LightBurn") or which("LightBurn.exe")
    if exe:
        return exe
    return None


# Adjust this to your Inkscape install if needed
DEFAULT_INKSCAPE_PATH = r"C:\Program Files\Inkscape\bin\inkscape.exe"


def _find_inkscape_exe():
    """Try to locate the Inkscape executable."""
    if os.path.isfile(DEFAULT_INKSCAPE_PATH):
        return DEFAULT_INKSCAPE_PATH
    exe = which("inkscape")
    if exe:
        return exe
    return None


def _export_drills_svg(board, out_path):
    """Export vias and through-hole pad drills as a simple SVG of circles."""
    try:
        iu_per_mm = pcbnew.FromMM(1.0)
    except Exception:
        iu_per_mm = 1.0

    holes = []  # (x_mm, y_mm, d_mm)

    # Vias
    for item in board.GetTracks():
        if hasattr(item, "GetDrill") and hasattr(item, "GetPosition"):
            try:
                pos = item.GetPosition()
                d = item.GetDrill()
            except Exception:
                continue
            try:
                x = pos.x / iu_per_mm
                y = pos.y / iu_per_mm
                dia = d / iu_per_mm
            except Exception:
                continue
            if dia > 0:
                holes.append((x, y, dia))

    # Pad drills
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            try:
                drill = pad.GetDrillSize()
                pos = pad.GetPosition()
            except Exception:
                continue
            try:
                dx = drill.x / iu_per_mm
                dy = drill.y / iu_per_mm
                x = pos.x / iu_per_mm
                y = pos.y / iu_per_mm
            except Exception:
                continue
            if dx <= 0 and dy <= 0:
                continue
            dia = max(dx, dy)
            holes.append((x, y, dia))

    if not holes:
        return

    xs = [h[0] for h in holes]
    ys = [h[1] for h in holes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    margin = 1.0
    min_x -= margin
    min_y -= margin
    max_x += margin
    max_y += margin
    width = max_x - min_x
    height = max_y - min_y

    def fmt(v):
        return ("%.4f" % v).rstrip("0").rstrip(".")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'version="1.1" '
            'viewBox="%s %s %s %s" width="%smm" height="%smm">\n'
            % (fmt(min_x), fmt(min_y), fmt(width), fmt(height), fmt(width), fmt(height))
        )
        f.write('  <g id="drills" fill="none" stroke="#0000ff" stroke-width="0.01">\n')
        for x, y, d in holes:
            f.write(
                '    <circle cx="%s" cy="%s" r="%s"/>\n'
                % (fmt(x), fmt(y), fmt(d / 2.0))
            )
        f.write("  </g>\n")
        f.write("</svg>\n")


class PlotLightBurnKiCadPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Plot via KiCad (LightBurn)"
        self.category = "LightBurn"
        self.description = "Export SVGs via KiCad + Inkscape and open in LightBurn"
        self.show_toolbar_button = True
        # Toolbar icon expected to live in the plugins/ folder of the package.
        # Use an absolute path so KiCad can always find it.
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, "lightburn_icon.png")
        self.icon_file_name = icon_path
        self.dark_icon_file_name = icon_path

    def Run(self):
        board = pcbnew.GetBoard()
        brd_path = board.GetFileName()
        if not brd_path:
            wx.MessageBox(
                "Board must be saved before plotting to SVG.",
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_WARNING,
            )
            return

        base_dir = os.path.dirname(brd_path)
        base_name = os.path.splitext(os.path.basename(brd_path))[0]
        out_dir = base_dir

        try:
            pctl = pcbnew.PLOT_CONTROLLER(board)
            popts = pctl.GetPlotOptions()

            # Basic plot options for SVG intended for LightBurn
            popts.SetOutputDirectory(out_dir)
            try:
                popts.SetPlotFrameRef(False)
            except Exception:
                pass
            try:
                popts.SetPlotValue(False)
                popts.SetPlotReference(False)
            except Exception:
                pass
            try:
                popts.SetPlotInvisibleText(False)
            except Exception:
                pass
            try:
                popts.SetExcludeEdgeLayer(False)
            except Exception:
                pass

            # Plot F.Cu, B.Cu, Edge.Cuts, and silkscreen as separate SVGs using KiCad's plotter
            top_svg = None
            bottom_svg = None
            edge_svg = None
            fsilk_svg = None
            bsilk_svg = None
            layers_to_plot = [
                ("F.Cu", base_name + "_kicad_top"),
                ("B.Cu", base_name + "_kicad_bottom"),
                ("Edge.Cuts", base_name + "_kicad_edge"),
                ("F.SilkS", base_name + "_kicad_fsilk"),
                ("B.SilkS", base_name + "_kicad_bsilk"),
            ]

            for layer_name, tag in layers_to_plot:
                try:
                    layer_id = board.GetLayerID(layer_name)
                except Exception:
                    continue
                pctl.SetLayer(layer_id)
                pctl.OpenPlotfile(tag, pcbnew.PLOT_FORMAT_SVG, "LightBurn SVG")
                pctl.PlotLayer()
                try:
                    fname = pctl.GetPlotFileName()
                except Exception:
                    # Fall back to constructing the name
                    fname = os.path.join(out_dir, tag + ".svg")
                if layer_name == "F.Cu":
                    top_svg = fname
                elif layer_name == "B.Cu":
                    bottom_svg = fname
                elif layer_name == "Edge.Cuts":
                    edge_svg = fname
                elif layer_name == "F.SilkS":
                    fsilk_svg = fname
                elif layer_name == "B.SilkS":
                    bsilk_svg = fname

            try:
                pctl.ClosePlot()
            except Exception:
                pass

        except Exception as e:
            wx.MessageBox(
                "Failed to plot SVG via KiCad:\n\n%s" % e,
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_ERROR,
            )
            return

        if not top_svg or not os.path.isfile(top_svg):
            wx.MessageBox(
                "KiCad did not produce a top SVG file.\n"
                "Please check your plot settings and try again.",
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_WARNING,
            )
            return

        # Generate drills SVG alongside plotted layers
        drills_svg = os.path.join(out_dir, base_name + "_kicad_drills.svg")
        try:
            _export_drills_svg(board, drills_svg)
        except Exception:
            drills_svg = None

        # Process the top and bottom SVGs via Inkscape to convert strokes to paths and union shapes
        inkscape_exe = _find_inkscape_exe()
        if not inkscape_exe:
            wx.MessageBox(
                "Could not find Inkscape.\n\n"
                "Please either:\n"
                f"  - Install Inkscape at:\n    {DEFAULT_INKSCAPE_PATH}\n"
                "  - Or add Inkscape to your PATH.\n\n"
                "The raw KiCad SVGs will be opened in LightBurn instead.",
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_WARNING,
            )
            processed_top_svg = top_svg
            processed_bottom_svg = bottom_svg
        else:
            # Top
            processed_top_svg = os.path.join(out_dir, base_name + "_kicad_top_lb.svg")
            actions_top = (
                "select-all:all;"
                "object-to-path;"
                "object-stroke-to-path;"
                "selection-ungroup;"
                "path-union;"
                f"export-filename:{processed_top_svg};"
                "export-do"
            )
            try:
                subprocess.run(
                    [inkscape_exe, top_svg, f"--actions={actions_top}"],
                    check=True,
                )
            except Exception as e:
                wx.MessageBox(
                    "Inkscape failed to process TOP SVG for LightBurn:\n\n%s\n\n"
                    "The raw KiCad TOP SVG will be used instead." % e,
                    "Plot via KiCad (LightBurn)",
                    style=wx.OK | wx.ICON_WARNING,
                )
                processed_top_svg = top_svg

            # Bottom (if we have one)
            if bottom_svg and os.path.isfile(bottom_svg):
                processed_bottom_svg = os.path.join(
                    out_dir, base_name + "_kicad_bottom_lb.svg"
                )
                actions_bot = (
                    "select-all:all;"
                    "object-to-path;"
                    "object-stroke-to-path;"
                    "selection-ungroup;"
                    "path-union;"
                    f"export-filename:{processed_bottom_svg};"
                    "export-do"
                )
                try:
                    subprocess.run(
                        [inkscape_exe, bottom_svg, f"--actions={actions_bot}"],
                        check=True,
                    )
                except Exception as e:
                    wx.MessageBox(
                        "Inkscape failed to process BOTTOM SVG for LightBurn:\n\n%s\n\n"
                        "The raw KiCad BOTTOM SVG will be used instead." % e,
                        "Plot via KiCad (LightBurn)",
                        style=wx.OK | wx.ICON_WARNING,
                    )
                    processed_bottom_svg = bottom_svg
            else:
                processed_bottom_svg = bottom_svg

        # Build a combined SVG containing all layers (top/bottom copper, edge, drills, silkscreen)
        combined_svg = None
        try:
            if not processed_top_svg or not os.path.isfile(processed_top_svg):
                raise RuntimeError("Processed top SVG missing")
            tree = ET.parse(processed_top_svg)
            root = tree.getroot()
            # Determine namespace
            if root.tag.startswith("{"):
                ns_uri = root.tag.split("}")[0][1:]
                svg_ns = "{" + ns_uri + "}"
            else:
                svg_ns = ""

            def is_defs(elem):
                tag = elem.tag
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                return tag == "defs"

            # Utility: apply a stroke color recursively to an element and its children
            def apply_stroke_recursive(elem, stroke_color):
                if stroke_color:
                    # Force stroke and fill to the desired color so LightBurn
                    # groups these shapes into the same colored layer.
                    elem.set("stroke", stroke_color)
                    elem.set("fill", stroke_color)
                    # Strip any inline stroke/fill from style attribute
                    style = elem.attrib.get("style")
                    if style:
                        parts = []
                        for part in style.split(";"):
                            part = part.strip()
                            if not part:
                                continue
                            if part.startswith("stroke:") or part.startswith("fill:"):
                                continue
                            parts.append(part)
                        if parts:
                            elem.set("style", ";".join(parts))
                        else:
                            elem.attrib.pop("style", None)
                for ch in list(elem):
                    apply_stroke_recursive(ch, stroke_color)

            # Wrap existing content into top copper group, recoloring to red
            g_top = ET.SubElement(root, svg_ns + "g", {"id": "copper_top"})
            for child in list(root):
                if child is g_top or is_defs(child):
                    continue
                root.remove(child)
                colored = copy.deepcopy(child)
                apply_stroke_recursive(colored, "#ff0000")
                g_top.append(colored)

            def append_svg_into_group(src_path, group_id, stroke_color=None):
                if not src_path or not os.path.isfile(src_path):
                    return
                try:
                    stree = ET.parse(src_path)
                    sroot = stree.getroot()
                except Exception:
                    return
                group = ET.SubElement(root, svg_ns + "g", {"id": group_id})
                for child in list(sroot):
                    if is_defs(child):
                        continue
                    colored = copy.deepcopy(child)
                    apply_stroke_recursive(colored, stroke_color)
                    group.append(colored)

            # Bottom copper
            if processed_bottom_svg and os.path.isfile(processed_bottom_svg):
                append_svg_into_group(processed_bottom_svg, "copper_bottom", "#00aa00")
            # Edge cuts
            if edge_svg and os.path.isfile(edge_svg):
                append_svg_into_group(edge_svg, "edge_cuts", "#000000")
            # Drills
            if drills_svg and os.path.isfile(drills_svg):
                append_svg_into_group(drills_svg, "drills", "#0000ff")
            # Silkscreen
            if fsilk_svg and os.path.isfile(fsilk_svg):
                append_svg_into_group(fsilk_svg, "silk_top", "#ffff00")
            if bsilk_svg and os.path.isfile(bsilk_svg):
                append_svg_into_group(bsilk_svg, "silk_bottom", "#ff00ff")

            combined_svg = os.path.join(out_dir, base_name + "_kicad_all_lb.svg")
            tree.write(combined_svg, encoding="utf-8", xml_declaration=True)
        except Exception:
            combined_svg = None

        exe = _find_lightburn_exe()
        if not exe:
            wx.MessageBox(
                "Could not find LightBurn.\n\n"
                "Please either:\n"
                "  - Install LightBurn at the default location, or\n"
                "  - Add LightBurn to your PATH.\n\n"
                "You can also edit DEFAULT_LIGHTBURN_PATH in the plugin code.",
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_ERROR,
            )
            return

        # Prefer combined SVG, fall back to processed top
        svg_to_open = combined_svg if combined_svg and os.path.isfile(combined_svg) else processed_top_svg
        try:
            subprocess.Popen([exe, svg_to_open], shell=False)
        except Exception as e:
            wx.MessageBox(
                "Failed to start LightBurn:\n\n%s" % e,
                "Plot via KiCad (LightBurn)",
                style=wx.OK | wx.ICON_ERROR,
            )
            return

        msg = "Plotted SVG via KiCad:\n%s" % top_svg
        if processed_top_svg != top_svg:
            msg += "\nProcessed TOP SVG via Inkscape:\n%s" % processed_top_svg
        if bottom_svg and os.path.isfile(bottom_svg):
            msg += "\nPlotted BOTTOM SVG via KiCad:\n%s" % bottom_svg
        if processed_bottom_svg and processed_bottom_svg != bottom_svg:
            msg += "\nProcessed BOTTOM SVG via Inkscape:\n%s" % processed_bottom_svg
        if drills_svg and os.path.isfile(drills_svg):
            msg += "\nDrills SVG:\n%s" % drills_svg
        if combined_svg and os.path.isfile(combined_svg):
            msg += "\nCombined all-layers SVG:\n%s" % combined_svg
        msg += "\n\nLightBurn launched:\n%s" % exe
        wx.MessageBox(
            msg,
            "Plot via KiCad (LightBurn)",
            style=wx.OK | wx.ICON_INFORMATION,
        )


# Register the plugin
PlotLightBurnKiCadPlugin().register()

