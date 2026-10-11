"""Icon lookup and key-image rendering (cairo + librsvg + Pango)."""

import base64
import io
import os
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
import cairo  # noqa: E402
from gi.repository import GdkPixbuf, Gio, Gtk, Pango, PangoCairo, Rsvg  # noqa: E402

KEY_SIZE = 144  # crisp on 72px (MK.2) and 96px (XL) keys; OpenDeck downscales
THUMB_SIZE = 40
FALLBACK_ICON = "application-x-executable"

MODES = ("full", "white", "black", "custom")

# Label style per rendering mode: (text colour, stroke colour, outline size)
LABEL_STYLE = {
    "black": ("#000000", "#FFFFFF", 0),
    "white": ("#FFFFFF", "#000000", 0),
    "custom": (None, "#000000", 1),  # None -> the custom colour
    "full": ("#FFFFFF", "#000000", 1),
}

_theme = None
_lock = threading.RLock()  # GTK icon theme and rendering are not thread-safe


def _icon_theme():
    """A display-independent icon theme matching the desktop's theme."""
    global _theme
    if _theme is None:
        _theme = Gtk.IconTheme.new()
        try:
            name = Gio.Settings.new("org.gnome.desktop.interface").get_string("icon-theme")
            if name:
                _theme.set_custom_theme(name)
        except Exception:
            pass
        # Make sure Flatpak icon exports are searched even if the plugin was
        # started with a minimal XDG_DATA_DIRS.
        paths = _theme.get_search_path()
        for extra in (
            Path.home() / ".local/share/flatpak/exports/share/icons",
            Path("/var/lib/flatpak/exports/share/icons"),
        ):
            if extra.is_dir() and str(extra) not in paths:
                _theme.append_search_path(str(extra))
    return _theme


def parse_color(value, default=(1.0, 1.0, 1.0, 1.0)):
    """Parse #RGB, #RGBA, #RRGGBB or #RRGGBBAA into an (r, g, b, a) tuple of floats."""
    if not isinstance(value, str):
        return default
    h = value.strip().lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "ff"
    if len(h) != 8:
        return default
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4, 6))
    except ValueError:
        return default


def resolve_icon_path(icon, size, symbolic):
    """Find a file for an Icon= value. Prefers '<name>-symbolic' when asked."""
    if icon and os.path.isabs(icon):
        return icon if os.path.isfile(icon) else None
    theme = _icon_theme()
    names = []
    if icon:
        stem = icon
        for ext in (".png", ".svg", ".xpm"):
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
        if symbolic:
            names.append(stem + "-symbolic")
        names.append(stem)
    for name in names:
        info = theme.lookup_icon(name, size, Gtk.IconLookupFlags.FORCE_SIZE)
        if info and info.get_filename():
            return info.get_filename()
        for ext in (".svg", ".png", ".xpm"):
            pixmap = f"/usr/share/pixmaps/{name}{ext}"
            if os.path.isfile(pixmap):
                return pixmap
    return None


def _load_icon_surface(path, size):
    """Render an icon file into a size x size ARGB surface, aspect preserved."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    if path.endswith(".svg") or path.endswith(".svgz"):
        handle = Rsvg.Handle.new_from_file(path)
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, size, size
        handle.render_document(cr, viewport)
    else:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
        ok, data = pixbuf.save_to_bufferv("png", [], [])
        img = cairo.ImageSurface.create_from_png(io.BytesIO(data))
        cr.set_source_surface(img, (size - img.get_width()) / 2, (size - img.get_height()) / 2)
        cr.paint()
    surface.flush()
    return surface


def icon_surface(icon, size, mode, color):
    """Icon rendered at `size`, recoloured for the mono modes."""
    mono = mode != "full"
    path = resolve_icon_path(icon, size, symbolic=mono) or resolve_icon_path(FALLBACK_ICON, size, mono)
    if not path:
        return cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    try:
        src = _load_icon_surface(path, size)
    except Exception:
        return cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    if not mono:
        return src
    # Mono: use the icon's alpha as a mask over a solid fill.
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(out)
    cr.set_source_rgba(*mode_color(mode, color))
    cr.mask_surface(src, 0, 0)
    out.flush()
    return out


def mode_color(mode, color):
    if mode == "white":
        return (1.0, 1.0, 1.0, 1.0)
    if mode == "black":
        return (0.0, 0.0, 0.0, 1.0)
    return parse_color(color)


def _label_layout(cr, text, width, size):
    """A centred, at most two-line layout that shrinks the font to fit."""
    layout = PangoCairo.create_layout(cr)
    layout.set_text(text, -1)
    layout.set_width(int(width * Pango.SCALE))
    layout.set_alignment(Pango.Alignment.CENTER)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_ellipsize(Pango.EllipsizeMode.END)
    layout.set_height(-2)  # max two lines
    font = Pango.FontDescription.from_string("Sans Bold")
    # Shrink until it fits on one line; below 11% of the key, accept two lines.
    for px in range(int(size * 0.15), int(size * 0.08) - 1, -1):
        font.set_absolute_size(px * Pango.SCALE)
        layout.set_font_description(font)
        if not layout.is_ellipsized() and (layout.get_line_count() == 1 or px <= size * 0.11):
            break
    return layout


def render_key(icon, mode, color, scale, label=None, size=KEY_SIZE):
    """Render the key image; returns PNG bytes.

    scale: 20-100 (% of the icon area); label: text drawn into the image or None.
    """
    with _lock:
        return _render_key(icon, mode, color, scale, label, size)


def _render_key(icon, mode, color, scale, label, size):
    scale = max(20, min(100, int(scale or 100)))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)

    pad = size * 0.04
    area_top, area_h = 0.0, float(size)
    layout = None
    if label:
        layout = _label_layout(cr, label, size - 2 * pad, size)
        _, logical = layout.get_pixel_extents()
        text_h = logical.height
        area_h = size - text_h - pad * 1.5
        area_top = pad / 2

    icon_px = max(1, int(min(size, area_h) * scale / 100))
    icon = icon_surface(icon, icon_px, mode, color)
    cr.set_source_surface(icon, (size - icon_px) / 2, area_top + (area_h - icon_px) / 2)
    cr.paint()

    if layout:
        text_rgb, stroke_rgb, outline = LABEL_STYLE.get(mode, LABEL_STYLE["full"])
        fill = parse_color(color) if text_rgb is None else parse_color(text_rgb)
        _, logical = layout.get_pixel_extents()
        cr.move_to(pad, size - logical.height - pad / 2)
        if outline:
            PangoCairo.layout_path(cr, layout)
            cr.set_source_rgba(*parse_color(stroke_rgb))
            cr.set_line_width(size / 36 * outline)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.stroke()
            cr.move_to(pad, size - logical.height - pad / 2)
        cr.set_source_rgba(*fill)
        PangoCairo.show_layout(cr, layout)

    surface.flush()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def data_url(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def thumbnail(icon, mode, color, size=THUMB_SIZE):
    return data_url(render_key(icon, mode, color, 100, None, size))
