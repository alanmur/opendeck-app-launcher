#!/usr/bin/env python3
"""Generate the App Launch plugin's icons (an app-grid glyph) with cairo."""

import math
from pathlib import Path

import cairo

OUT = Path(__file__).resolve().parent.parent / "icons"


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def grid(cr, size, margin, rgba):
    """3x3 grid of rounded tiles filling size minus margin."""
    area = size - 2 * margin
    gap = area * 0.12
    tile = (area - 2 * gap) / 3
    cr.set_source_rgba(*rgba)
    for row in range(3):
        for col in range(3):
            rounded(cr, margin + col * (tile + gap), margin + row * (tile + gap), tile, tile, tile * 0.28)
    cr.fill()


def icon(name, size, margin, rgba, background=None):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    if background:
        cr.set_source_rgba(*background)
        rounded(cr, 0, 0, size, size, size * 0.2)
        cr.fill()
    grid(cr, size, margin, rgba)
    surface.write_to_png(str(OUT / name))


OUT.mkdir(parents=True, exist_ok=True)
WHITE = (1, 1, 1, 1)
BLUE = (0.23, 0.51, 0.96, 1)
for scale, suffix in ((1, ""), (2, "@2x")):
    # Plugin icon (store/list): white grid on blue tile.
    icon(f"plugin{suffix}.png", 144 * scale, 30 * scale, WHITE, background=BLUE)
    # Category and action-list icons: monochrome white glyphs.
    icon(f"category{suffix}.png", 28 * scale, 4 * scale, WHITE)
    icon(f"action{suffix}.png", 20 * scale, 2 * scale, WHITE)
    # Default key image before an app is chosen.
    icon(f"key{suffix}.png", 72 * scale, 20 * scale, (1, 1, 1, 0.55))
print("icons written to", OUT)
