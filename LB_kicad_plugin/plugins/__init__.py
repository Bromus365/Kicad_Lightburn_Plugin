"""
Plugin package for the LightBurn KiCad action plugin.

KiCad's Plugin and Content Manager expects Python plugins to live in a
`plugins` package. The action plugin is defined in:

  - lb_plot_lightburn_kicad.py  (KiCad plotter + Inkscape + LightBurn)
"""

from .lb_plot_lightburn_kicad import *  # noqa: F401,F403


