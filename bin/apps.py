"""Discovery and parsing of installed desktop applications (.desktop files)."""

import os
import shutil
from pathlib import Path

HOME = Path.home()

# Searched in priority order: the first file found for a desktop ID wins, so
# user overrides in ~/.local shadow system-wide entries of the same name.
APP_DIRS = [
    HOME / ".local/share/applications",
    HOME / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]


def parse_desktop_file(path):
    """Return the [Desktop Entry] group of a .desktop file as a dict, or None."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    entry = {}
    in_group = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if in_group:
                break  # [Desktop Entry] is over; actions follow
            in_group = line == "[Desktop Entry]"
            continue
        if in_group and "=" in line:
            key, _, value = line.partition("=")
            entry.setdefault(key.strip(), value.strip())
    return entry or None


def _locale_candidates(lang):
    """Keys to try for a locale per the Desktop Entry spec, most specific first.

    "sr_RS@latin" -> ["sr_RS@latin", "sr_RS", "sr@latin", "sr"]
    """
    if not lang:
        return []
    lang = lang.split(".")[0]  # drop any encoding, e.g. en_US.UTF-8
    base, _, modifier = lang.partition("@")
    language, _, country = base.partition("_")
    out = []
    if country and modifier:
        out.append(f"{language}_{country}@{modifier}")
    if country:
        out.append(f"{language}_{country}")
    if modifier:
        out.append(f"{language}@{modifier}")
    out.append(language)
    return out


def localized(entry, key, lang):
    for loc in _locale_candidates(lang):
        value = entry.get(f"{key}[{loc}]")
        if value:
            return value
    return entry.get(key, "")


def system_language():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX"):
            return value.split(".")[0]
    return "en"


def _is_true(value):
    return (value or "").strip().lower() == "true"


def _shown_in_current_desktop(entry):
    desktops = {d for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d}
    only = {d for d in entry.get("OnlyShowIn", "").split(";") if d}
    never = {d for d in entry.get("NotShowIn", "").split(";") if d}
    if only and not (only & desktops):
        return False
    return not (never & desktops)


def _try_exec_ok(entry):
    try_exec = entry.get("TryExec")
    if not try_exec:
        return True
    if os.path.isabs(try_exec):
        return os.access(try_exec, os.X_OK)
    return shutil.which(try_exec) is not None


def iter_desktop_files():
    """Yield (desktop_id, path) for every .desktop file, highest priority first."""
    seen = set()
    for base in APP_DIRS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.desktop")):
            # Files in subdirectories get IDs with '/' replaced by '-' (XDG spec).
            desktop_id = str(path.relative_to(base))[: -len(".desktop")].replace("/", "-")
            if desktop_id in seen:
                continue
            seen.add(desktop_id)
            yield desktop_id, path


def scan_apps(lang):
    """Return the launchable applications, sorted by localized name."""
    apps = []
    for desktop_id, path in iter_desktop_files():
        entry = parse_desktop_file(path)
        if not entry or entry.get("Type") != "Application":
            continue
        if _is_true(entry.get("NoDisplay")) or _is_true(entry.get("Hidden")):
            continue
        if not _shown_in_current_desktop(entry) or not _try_exec_ok(entry):
            continue
        name = localized(entry, "Name", lang)
        if not name:
            continue
        apps.append({
            "id": desktop_id,
            "path": str(path),
            "name": name,
            "exec": entry.get("Exec", ""),
            "icon": localized(entry, "Icon", lang),
        })
    apps.sort(key=lambda a: a["name"].casefold())
    return apps


def find_app(desktop_id, lang, path_hint=None):
    """Look up one application by desktop ID (falling back to a known path)."""
    for did, path in iter_desktop_files():
        if did == desktop_id:
            break
    else:
        path = Path(path_hint) if path_hint and Path(path_hint).is_file() else None
    if path is None:
        return None
    entry = parse_desktop_file(path) or {}
    return {
        "id": desktop_id,
        "path": str(path),
        "name": localized(entry, "Name", lang) or desktop_id,
        "exec": entry.get("Exec", ""),
        "icon": localized(entry, "Icon", lang),
    }
