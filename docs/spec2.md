# App Launch — Build Specification (v2)

A precise specification for building the **App Launch** plugin for [OpenDeck](https://github.com/nekename/OpenDeck). It is written so that an AI coding assistant (Claude) can recreate the plugin in this repository from scratch, test it, and ask a human to run the checks that need real hardware. It is also written for human maintainers: every rule has a reason, every number is stated once in a table, and every test has an ID you can cite.

Replaces the original `spec.md` (the first-draft brief).

## How to use this document

**To rebuild or extend the plugin with an AI:** give the assistant this whole file as the prompt, plus this instruction:

> Build the plugin in this repository exactly as specified in `docs/spec2.md`. Follow Sections 1–12 to build, then run every automated test in Section 13 and report the result of each by its ID. When you reach a human test in Section 14, stop, give me the steps, and wait for my answer. Do not restart OpenDeck, commit, push or publish anything without asking me first.

**To change the plugin:** edit the relevant section and keep the test IDs in step. Section 15 explains where each kind of change belongs.

**Conventions**

- **MUST / MUST NOT** mark requirements. A build that breaks one is wrong.
- **SHOULD** marks strong defaults that may be changed with a reason.
- Values in code font are exact (file names, event names, constants).
- Test IDs: `A-nn` automated, `H-nn` human.

---

## 1. Summary

### 1.1 What it does

The plugin puts installed desktop applications on Stream Deck keys. The user drags **App Launch → Launch Application** onto a key in OpenDeck, opens the settings panel, and picks an application from a searchable list. The key then shows the application's icon (and optionally its name). Pressing the key launches the application.

### 1.2 Shape of the solution

Two parts that talk through OpenDeck:

| Part | Technology | Can touch the filesystem? | Job |
| --- | --- | --- | --- |
| **Backend** (`bin/plugin.py` and helpers) | Python 3, standard library plus system GTK libraries | Yes | Scans `.desktop` files, finds and renders icons, draws key images, launches apps |
| **Settings panel** (`pi/`) | Plain HTML, CSS and JavaScript, no build step | No | Shows options, the application picker, and the current key |

The panel never reads files. It asks the backend for data and receives it as JSON through OpenDeck.

### 1.3 Decisions that are fixed

These were chosen deliberately. Do not change them without a reason that outweighs the stated one.

| # | Decision | Reason |
| --- | --- | --- |
| D1 | The label and the scaled icon are **drawn into the key image** by the backend by default. | OpenDeck's plugin API can set a key's image and title text but not text colour, outline or image scale. Drawing the image gives full control. A setting lets the user choose OpenDeck's own title instead (see 7.4). |
| D2 | Keys launch with **`gtk-launch <desktop-id>`**, falling back to `gio launch <path>`. | `gtk-launch` takes a desktop ID, not an `Exec` line, and handles Flatpak apps and `%U`/`%f` placeholders correctly. |
| D3 | The plugin **never edits OpenDeck's profile files**. It uses the plugin API (`setImage`, `setTitle`, `setSettings`). | OpenDeck holds profiles in memory and can overwrite edits made on disk. |
| D4 | There is **no backup or undo script**. | An earlier draft of the spec had one. It is not needed: the plugin only changes a key when the user presses OK or edits an option, and the user can change the key again. |
| D5 | The backend uses **no third-party Python packages**. It includes its own minimal WebSocket client. | Fedora Workstation does not ship `websockets` or `websocket-client`. The plugin must work on a stock install. |
| D6 | The backend **never repaints a key on startup or on any background event**. | OpenDeck saves the image and title it was given. Repainting at startup would overwrite anything saved for the key. (See rule R1.) |
| D7 | Rendering resolution is **144×144 px**. | Sharp on both 72 px and 96 px keys. OpenDeck scales the image down. |

---

## 2. Environment

| Item | Requirement |
| --- | --- |
| OS | Linux. Developed and tested on Fedora Workstation 44 (GNOME). |
| OpenDeck | **2.14.0 or later.** Version 2.12.1 has a bug that resets the icons of other keys to the default grid icon when a new action is added. The bug is in OpenDeck, not the plugin, and was fixed upstream (pull request #387) in 2.14.0. |
| Python | 3. Developed and tested on 3.14; older 3.x releases were not tried. |
| Python modules | `gi` (PyGObject), `cairo` (pycairo). Standard library for everything else. |
| GObject typelibs | `Gtk 3.0`, `Rsvg 2.0`, `GdkPixbuf 2.0`, `Pango 1.0`, `PangoCairo 1.0`, plus `Gio` |
| Programs | `gtk-launch`, `gio` |
| Tools used only for testing | `node` (syntax check), a Chromium-based browser such as `brave-browser` (headless panel tests), `ImageMagick` `magick` (image montage), `zip`, `unzip`, `git` |

OpenDeck installs plugins by folder under `~/.config/opendeck/plugins/`. The folder name MUST be `cloud.caesium.applaunch.sdPlugin`. OpenDeck uses the folder name, not the manifest `UUID`, to identify the plugin (it appears as `cloud.caesium.applaunch.sdPlugin` in OpenDeck's log and in the `-pluginUUID` argument).

### 2.1 How OpenDeck behaves (facts the build depends on)

- OpenDeck scans for plugins **only at startup**. After adding a plugin or changing `manifest.json` the user MUST fully quit OpenDeck (tray menu → Quit; closing the window only hides it) and start it again. If a new copy is started while one is hidden in the tray, it hands over to the old one and exits, so the plugin never loads.
- OpenDeck starts the backend as: `plugin.py -port N -pluginUUID UUID -registerEvent EVENT -info JSON`, using the Elgato Stream Deck plugin protocol over a WebSocket at `ws://127.0.0.1:N`. It runs `.py` files directly, so `bin/plugin.py` MUST be executable and start with `#!/usr/bin/env python3`.
- OpenDeck creates a settings-panel instance **for every configured key at startup**, not only the selected one. So the panel sends `hello` once per key when OpenDeck starts, and anything the panel does on load happens for all keys.
- OpenDeck saves each key's image as `~/.config/opendeck/images/<device>/<profile>/<Controller>.<position>.<index>/0.png` and records the title text in the profile. These survive restarts.
- OpenDeck stores per-key plugin data in the profile as the key's `settings` object. The plugin receives it in the `willAppear` event and writes it with `setSettings`.
- OpenDeck stores plugin-wide data (global settings) in `~/.config/opendeck/settings/<plugin-folder-name>.json`.

---

## 3. Repository layout

The repository root IS the plugin. The repository is cloned straight into `~/.config/opendeck/plugins/cloud.caesium.applaunch.sdPlugin`.

```
.
├── manifest.json            plugin and action definition (Section 4)
├── README.md                user documentation (Section 11.1)
├── LICENSE                  MIT, "Copyright (c) 2026 Caesium Cloud"
├── .gitignore               __pycache__/  applaunch.log  debug  dist/
├── build.sh                 builds dist/cloud.caesium.applaunch.sdPlugin.zip (Section 11.3)
├── bin/
│   ├── plugin.py            entry point: WebSocket client, event handling (Section 6.3)
│   ├── apps.py              .desktop discovery and parsing (Section 6.1)
│   └── render.py            icon lookup and key rendering (Section 6.2)
├── pi/
│   ├── index.html           settings panel markup (Section 7)
│   ├── pi.css               settings panel styles
│   ├── pi.js                settings panel logic
│   └── languages.js         language-code table and helpers (Appendix A)
├── icons/                   plugin icons, generated by tools/make_icons.py (Section 8)
│   ├── plugin.png  plugin@2x.png      144 and 288 px, white grid on a blue tile
│   ├── category.png  category@2x.png  28 and 56 px, white grid
│   ├── action.png  action@2x.png      20 and 40 px, white grid
│   └── key.png  key@2x.png            72 and 144 px, translucent grid (default key image)
├── tools/
│   └── make_icons.py        generates icons/ with cairo
└── docs/
    ├── screenshot.png       screenshot used by the README
    └── spec2.md             this file
```

Files created at runtime and NOT committed: `applaunch.log`, `debug`, `__pycache__/`, `dist/`.

---

## 4. `manifest.json`

The file MUST be valid JSON and MUST contain exactly this content (tabs for indentation):

```json
{
	"Name": "App Launch",
	"Description": "Launch installed desktop applications, with their icons on the key.",
	"Author": "Caesium Cloud",
	"Version": "1.0.0.0",
	"UUID": "cloud.caesium.applaunch",
	"SDKVersion": 2,
	"Icon": "icons/plugin",
	"Category": "App Launch",
	"CategoryIcon": "icons/category",
	"CodePathLin": "bin/plugin.py",
	"CodePaths": {
		"x86_64-unknown-linux-gnu": "bin/plugin.py",
		"aarch64-unknown-linux-gnu": "bin/plugin.py"
	},
	"OS": [
		{
			"Platform": "linux"
		}
	],
	"Software": {
		"MinimumVersion": "6.4"
	},
	"Actions": [
		{
			"Name": "Launch Application",
			"UUID": "cloud.caesium.applaunch.launch",
			"Icon": "icons/action",
			"Tooltip": "Launch an installed desktop application",
			"PropertyInspectorPath": "pi/index.html",
			"Controllers": ["Keypad"],
			"SupportedInMultiActions": true,
			"States": [
				{
					"Image": "icons/key",
					"TitleAlignment": "bottom",
					"FontSize": 12
				}
			]
		}
	]
}
```

Rules:

- The action `UUID` MUST start with `<plugin UUID>.` (`cloud.caesium.applaunch.`). The OpenAction catalogue check uses this prefix as the "bundle ID".
- `Name` and `Author` MUST be reproduced exactly in the catalogue entry when publishing (Section 12).
- Icon paths are written **without** the `.png` extension and without `@2x`. OpenDeck finds the `@2x` variant itself.

---

## 5. Data model

### 5.1 Per-key settings

Stored by OpenDeck in the key's `settings` object. Written by the backend with `setSettings`.

```json
{
  "app": {
    "id": "org.gnome.Nautilus",
    "path": "/usr/share/applications/org.gnome.Nautilus.desktop",
    "name": "Files",
    "exec": "nautilus --new-window %U",
    "icon": "org.gnome.Nautilus"
  },
  "options": {
    "lang": "en_US",
    "mode": "full",
    "color": "#FFFFFFFF",
    "scale": 100,
    "renderLabels": true
  }
}
```

An unconfigured key has `settings` equal to `{}`.

### 5.2 Options

| Field | Type | Allowed values | Default | Meaning |
| --- | --- | --- | --- | --- |
| `lang` | string | a language code, e.g. `en_US`, `de`, `pt_BR`, `sr@latin` | the system language (see 6.1.3) | Language for the application's name |
| `mode` | string | `full`, `white`, `black`, `custom` | `full` | How the icon is coloured (see 6.2.3) |
| `color` | string | `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA` (hex, case-insensitive) | `#FFFFFFFF` | Colour used in `custom` mode, and for custom-mode label text. Alpha is supported. |
| `scale` | integer | 20 to 100, in steps of 5 | `100` | Icon size as a percentage of the available icon area |
| `renderLabels` | boolean | `true`, `false` | `true` | `true`: draw the name into the image. `false`: set the name as OpenDeck's key title. |

### 5.3 Global settings (shared defaults)

Stored by OpenDeck at `settings/cloud.caesium.applaunch.sdPlugin.json`. Written by the backend with `setGlobalSettings` whenever the user changes an option in the panel. Same fields as 5.2. May be `{}` or missing fields.

Global settings are **defaults for keys that have no app yet**. A configured key MUST always use its own `options`, never the global ones.

---

## 6. Backend

### 6.1 `bin/apps.py` — application discovery

#### 6.1.1 Search folders, in priority order

1. `~/.local/share/applications`
2. `~/.local/share/flatpak/exports/share/applications`
3. `/var/lib/flatpak/exports/share/applications`
4. `/usr/local/share/applications`
5. `/usr/share/applications`

Every `*.desktop` file is found recursively. The **desktop ID** is the path relative to its folder, minus `.desktop`, with `/` replaced by `-`. If two files have the same desktop ID, the **earlier folder wins** (so a user's own file overrides a system one).

#### 6.1.2 Parsing

Read the `[Desktop Entry]` group only; stop at the next group. Ignore blank lines and `#` comments. The first occurrence of a key wins. Read files as UTF-8, replacing undecodable bytes.

An entry is **listed** only if all of these hold:

- `Type=Application`
- `NoDisplay` and `Hidden` are not `true`
- it passes `OnlyShowIn` / `NotShowIn` against `XDG_CURRENT_DESKTOP` (split on `:`)
- `TryExec`, if present, resolves to an executable (absolute path, or found on `PATH`)
- it has a non-empty name

The list is sorted by name, case-insensitively.

For each entry capture: `id`, `path`, `name` (localised, 6.1.3), `exec` (the raw `Exec=` value), `icon` (the `Icon=` value, localised the same way).

#### 6.1.3 Localisation

Given a language code such as `sr_RS@latin`, try these keys in order and use the first that exists: `Name[sr_RS@latin]`, `Name[sr_RS]`, `Name[sr@latin]`, `Name[sr]`, then plain `Name`. (A code without a country or modifier tries just `Name[xx]` then `Name`.) Strip any encoding suffix first (`en_US.UTF-8` → `en_US`).

The system language is the first of `LC_ALL`, `LC_MESSAGES`, `LANG` that is set and is not `C` or `POSIX`, with the encoding removed; `en` if none.

#### 6.1.4 Functions

- `scan_apps(lang)` returns the sorted list of dicts described above.
- `find_app(desktop_id, lang, path_hint=None)` returns one app dict, or `None`. It searches by desktop ID; if not found it falls back to `path_hint` when that file exists. The name is localised with `lang`; if the localised name is empty it falls back to the desktop ID.
- `system_language()` as in 6.1.3.

### 6.2 `bin/render.py` — icons and key images

Uses `cairo`, `Rsvg`, `GdkPixbuf`, `Gtk.IconTheme`, `Pango` and `PangoCairo` through PyGObject.

#### 6.2.1 Constants

| Name | Value |
| --- | --- |
| `KEY_SIZE` | `144` |
| `THUMB_SIZE` | `40` (list and panel thumbnails) |
| `FALLBACK_ICON` | `application-x-executable` |
| scale range | 20 to 100 (values outside are clamped) |

#### 6.2.2 Finding the icon file

`resolve_icon_path(icon, size, symbolic)`:

- If `icon` is an absolute path, use it if the file exists, otherwise return nothing.
- Otherwise strip a trailing `.png`, `.svg` or `.xpm`, then look up names in a `Gtk.IconTheme.new()` (a theme object that needs no display) set to the desktop's icon theme (`org.gnome.desktop.interface icon-theme` via `Gio.Settings`; ignore failure). The search path MUST also include `~/.local/share/flatpak/exports/share/icons` and `/var/lib/flatpak/exports/share/icons` when those folders exist.
- When `symbolic` is true, try `<name>-symbolic` **before** `<name>`.
- Use `FORCE_SIZE`. As a last resort check `/usr/share/pixmaps/<name>.{svg,png,xpm}`.
- If nothing is found for the app, use `FALLBACK_ICON`; if even that fails, draw nothing for the icon.

#### 6.2.3 Colour modes

| `mode` | Icon rendering | Notes |
| --- | --- | --- |
| `full` | The icon's own colours | |
| `white` | Solid white `#FFFFFF`, using the icon's alpha as a mask | Prefers the `-symbolic` icon |
| `black` | Solid black `#000000`, using the icon's alpha as a mask | Prefers the `-symbolic` icon |
| `custom` | Solid `color` (including its alpha), using the icon's alpha as a mask | Prefers the `-symbolic` icon |

Loading an icon: SVG and SVGZ with `Rsvg.Handle.new_from_file` and `render_document`; everything else with `GdkPixbuf` (`new_from_file_at_scale`, aspect preserved, centred). The result is an ARGB surface of the requested size on a **transparent** background.

**Pitfall:** `Rsvg.Rectangle` MUST be created empty and then have its `x`, `y`, `width`, `height` attributes assigned. Passing them as keyword arguments raises `TypeError` in PyGObject, and because errors are caught the result is silently a blank icon.

`parse_color` accepts `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA` (leading `#` optional) and returns `(r, g, b, a)` floats 0 to 1; anything invalid returns the default (opaque white).

#### 6.2.4 Rendering a key

`render_key(icon, mode, color, scale, label=None, size=144)` returns PNG bytes. All drawing is serialised with a re-entrant lock (GTK's icon theme is not thread-safe). Steps:

1. Create a transparent `size × size` ARGB surface.
2. `pad = size × 0.04`. If there is a label, build its layout (below) and measure its height `text_h`; the icon area is then `area_h = size − text_h − pad × 1.5` starting at `area_top = pad / 2`. With no label the icon area is the whole key.
3. Icon size in pixels: `max(1, int(min(size, area_h) × scale / 100))`. Draw it centred in the icon area.
4. If there is a label, draw it centred horizontally at the bottom: top of text at `size − text_h − pad / 2`, left at `pad`, width `size − 2 × pad`.

**Label layout.** Font "Sans Bold", centred, word-wrap with character fallback, ellipsise at the end, at most two lines. Try font pixel sizes from `int(size × 0.15)` down to `int(size × 0.08)`. Use the first size where the text is not ellipsised and either fits on one line or the size is at most `size × 0.11`.

**Label style by mode:**

| `mode` | Text colour | Outline colour | Outline width |
| --- | --- | --- | --- |
| `black` | `#000000` | `#FFFFFF` | none (0) |
| `white` | `#FFFFFF` | `#000000` | none (0) |
| `custom` | the custom `color` | `#000000` | 1 |
| `full` | `#FFFFFF` | `#000000` | 1 |

Outline width `n` means the text path is stroked first with line width `size / 36 × n`, round joins, then the text is filled on top. Width 0 means no stroke.

`thumbnail(icon, mode, color, size=40)` returns a `data:image/png;base64,…` URL of the icon alone (no label, scale 100).

`data_url(png_bytes)` returns `data:image/png;base64,<base64>`.

### 6.3 `bin/plugin.py` — entry point

#### 6.3.1 Start-up

- Parse the command line as alternating `-name value` pairs. Use `-port`, `-pluginUUID`, `-registerEvent`. Ignore `-info`.
- Connect to `127.0.0.1:<port>`, send `{"event": <registerEvent>, "uuid": <pluginUUID>}`, then `{"event": "getGlobalSettings", "context": <pluginUUID>}`.
- Logging goes to `applaunch.log` in the plugin folder, **recreated on each start** (file mode `w`). Level is `INFO`, or `DEBUG` when the environment variable `APPLAUNCH_DEBUG` is set or a file named `debug` exists in the plugin folder. At `DEBUG` log every event received (`<- event context`) and sent (`-> event context`). Log uncaught exceptions with a traceback.
- Exit cleanly when the socket closes.

#### 6.3.2 WebSocket client

A minimal RFC 6455 client using only the standard library: HTTP upgrade handshake; text frames up to 64-bit lengths; client frames always masked; reply to ping with pong; ignore pong; return `None` on close. Sending is guarded by a lock because several threads send.

#### 6.3.3 Events received from OpenDeck

| Event | Behaviour |
| --- | --- |
| `willAppear`, `didReceiveSettings` | Remember `payload.settings` for the context. **Do nothing else — no drawing (rule R1).** |
| `willDisappear` | Forget the context's settings. |
| `didReceiveGlobalSettings` | Remember `payload.settings` as the shared options. |
| `keyDown` | Launch the key's app on a new thread (6.3.5). Use `payload.settings`, else the remembered settings. |
| `sendToPlugin` | Handle a settings-panel request (6.3.4) on a new thread, so scanning and rendering never block the read loop. An exception there is logged and reported to the panel as `{"type":"error","message":…}`. |
| anything else | Ignore. |

A bad message MUST be logged and skipped, never crash the loop.

#### 6.3.4 Settings-panel requests

All arrive as `sendToPlugin` with `payload.request`. Replies go back with `sendToPropertyInspector` to the same `context`. Every message the backend sends includes `"action": "cloud.caesium.applaunch.launch"`, except `setGlobalSettings`.

| `request` | Input fields | Backend action | Reply (`payload`) |
| --- | --- | --- | --- |
| `hello` | none | none | `{"type":"hello","systemLanguage","options":<shared options>,"keyOptions":<this key's options or null>,"thumb":<thumbnail of this key's app or "">}` |
| `saveOptions` | `options` | remember as shared options; send `setGlobalSettings` (context = plugin UUID) | none |
| `getApps` | `lang`, `mode`, `color` | `scan_apps(lang)`; a thumbnail per app with the given mode and colour (a failed thumbnail gives `""` and is logged) | `{"type":"apps","apps":[{"id","path","name","thumb"}]}` |
| `apply` | `app` (`id`, `path`), `options` | see below | `{"type":"applied","settings":<new settings>,"thumb":…}`, or `{"type":"error","message":"Application '<id>' not found"}` |

**`apply` in detail:**

1. `app = find_app(id, options.lang or system language, path)`. If not found, reply with the error and stop.
2. New settings are `{"app": app, "options": options}`.
3. Decide whether the **title** changed: true if the app ID differs, or the app name differs, or `renderLabels` differs from the previous settings (a missing value counts as `true`).
4. Remember the new settings; send `setSettings`.
5. Paint the key (6.3.6), sending the title only if step 3 said it changed.
6. Reply `applied`.

#### 6.3.5 Launching

1. No app in the settings → send `showAlert` and stop.
2. Run `gtk-launch <app.id>` with `XDG_DATA_DIRS` extended to include the two Flatpak export folders (`~/.local/share/flatpak/exports/share`, `/var/lib/flatpak/exports/share`) when absent. Standard input, output and error go to `/dev/null`; use `start_new_session=True` so the app outlives the plugin; time out after 15 s.
3. If that fails and `app.path` is set, run `gio launch <app.path>` the same way.
4. If both fail (or an `OSError`/timeout occurs), log it and send `showAlert`.

#### 6.3.6 Painting a key

Only called from `apply` (rule R1).

- `render_labels = options.renderLabels` (default `true`).
- Render with `render_key(app.icon, options.mode, options.color, options.scale, label)` where `label` is the app name when `render_labels` is true, otherwise none.
- Send `setImage` with `{"image": <data URL>, "target": 0}`.
- If the title is to be sent: send `setTitle` with `{"title": "" if render_labels else app.name, "target": 0}`.

### 6.4 Behaviour rules (invariants)

| ID | Rule | Reason |
| --- | --- | --- |
| **R1** | The backend MUST NOT send `setImage` or `setTitle` in response to `willAppear`, `didReceiveSettings`, `didReceiveGlobalSettings`, `hello`, `getApps`, `saveOptions`, or any other background event. It sends them only inside `apply`. | OpenDeck persists them. Repainting on startup overwrote values saved for every key. |
| **R2** | A configured key MUST use its own `options`. The settings panel MUST show a configured key's own options, not the shared ones. | Otherwise changing one option applies all the shared defaults to that key. |
| **R3** | `apply` MUST affect only the key it names. | The user changes one key at a time. |
| **R4** | `apply` MUST NOT send `setTitle` when only scale, colour or mode changed. | Text the user edited in OpenDeck's own key editor must survive. |
| **R5** | The plugin MUST NOT write files other than `applaunch.log`. | It runs on the user's machine with their permissions. |
| **R6** | Anything slow (scanning, rendering) MUST run off the WebSocket read thread. | A slow request would stall key presses. |

---

## 7. Settings panel (`pi/`)

OpenDeck loads `pi/index.html` in a web view and calls the global function `connectElgatoStreamDeckSocket(inPort, inPropertyInspectorUUID, inRegisterEvent, inInfo, inActionInfo)`. `inActionInfo` is a JSON string containing `action`, `context` and `payload.settings` (the key's settings).

The panel connects to `ws://localhost:<port>`, sends `{"event": inRegisterEvent, "uuid": inPropertyInspectorUUID}` on open, then sends `hello`. Requests go out as `{"event":"sendToPlugin","action":<action>,"context":<context>,"payload":{"request":…}}`. It listens for `sendToPropertyInspector` (replies) and `didReceiveSettings` (updates its copy of the key's settings).

### 7.1 Layout, top to bottom

Dark theme matching OpenDeck (background `#2d2d2d`). Labels on the left (96 px wide, right-aligned), controls on the right.

1. **Error box** (hidden unless there is an error), red text and border.
2. **Application**: a 28 px icon thumbnail (hidden if none) and the app name, or "None selected" in grey.
3. **Select Application…** button.
4. **Language**: a text box (90 px wide) and, beside it, the language's own name. Unknown codes show "Unknown language" and mark the box as invalid.
5. **Icon colour**: four radio buttons, "Full colour", "White", "Black", "Custom". On the Custom row: a text box for the colour (98 px, monospace, placeholder `#RRGGBBAA`) and a **swatch**.
6. **Image scale**: a range slider 20 to 100, step 5, and the value shown as `NN%`.
7. **Label**: two radio buttons, "Render into image" and "Set as key title".

There is **no** hint text saying settings apply when OK is pressed (options apply immediately — see 7.3).

The swatch is a 22 px rounded square over a checkerboard (so transparency shows), filled with the current colour. Clicking it opens the browser's colour picker. The picker is RGB only, so choosing a colour keeps the alpha digits from the text box.

The colour text box and swatch are **enabled only when "Custom" is selected**. An invalid colour marks the box red (only in Custom mode).

### 7.2 Loading

1. Show the key's current app from `inActionInfo.payload.settings.app`.
2. On `hello`: options = defaults, overlaid with the shared options, overlaid with `keyOptions`. If `lang` is still empty use the system language from the reply, normalised (7.5). Show the options, and show the thumbnail from the reply.

Defaults: `{lang: "", mode: "full", color: "#FFFFFFFF", scale: 100, renderLabels: true}`.

### 7.3 Changing options — immediate effect

Any change to language, colour mode, colour, scale or label setting:

1. Updates the panel's options and controls at once.
2. After **300 ms with no further change** (debounce): sends `saveOptions`, then sends `apply` for the current app with the full options.

`apply` is skipped when: the key has no app, or `mode` is `custom` and the colour is invalid. A language code that does not normalise (7.5) is neither saved nor applied.

Typing in the language box saves as you type if the code is valid; on leaving the box a valid code is rewritten in normalised form.

### 7.4 Label setting

- **Render into image** (`renderLabels: true`): the name is drawn into the image by the backend; OpenDeck's title is set to empty.
- **Set as key title** (`renderLabels: false`): the image has no label; OpenDeck's title is set to the app name. The user can then style the title in OpenDeck's own key editor.

### 7.5 Language box

Normalise: `^([a-zA-Z]{2,3})(?:[-_]([a-zA-Z]{2}))?(?:@([a-zA-Z]+))?$` → language lower-case, country upper-case, modifier lower-case, joined as `ll_CC@mod`. Examples: `pt-br` → `pt_BR`, `sr@Latin` → `sr@latin`. Anything else is invalid.

Display name: look the normalised code up in the table (Appendix A). If missing, try the base language and show `<name> (<code>)`, for example `es_MX` → `Español (es_MX)`. Otherwise show "Unknown language".

### 7.6 Application picker (modal)

Opened by **Select Application…**. Not opened if mode is `custom` and the colour is invalid (show an error instead).

- A full-panel overlay (dimmed background) with a dialog: header "Select Application" and a **search box** (filters by name or ID, case-insensitive; focused on open); a **single-select list**; footer with a status line ("N of M applications"), **Cancel**, and **OK** (disabled until an item is selected, blue).
- On open it clears the list, shows "Loading applications…", and sends `getApps` with the current `lang`, `mode`, `color`.
- Each list row: a 32 px thumbnail on a grey backing (so white icons are visible), the localised name, and the desktop ID in small grey text beneath. The key's current app is pre-selected and scrolled into view.
- Keyboard: Up/Down move the selection, Enter confirms, Escape cancels. Double-click a row to confirm.
- **Cancel** (or Escape) closes the dialog and changes nothing.
- **OK** disables itself, shows "Applying…", and sends `apply` with the chosen app (`id` and `path`) and the current options. The dialog closes when the `applied` reply arrives. An `error` reply is shown and OK is re-enabled.

### 7.7 Files

- `index.html` loads `pi.css`, `languages.js`, `pi.js` (in that order for the scripts) and contains no inline script.
- No external resources, fonts or CDNs.
- `pi.js` MUST pass `node --check`.

---

## 8. Icons (`icons/`, `tools/make_icons.py`)

Generated with cairo by `tools/make_icons.py`. A 3×3 grid of rounded squares (gap 12% of the drawing area, corner radius 28% of a tile).

| File | Size | Margin | Appearance |
| --- | --- | --- | --- |
| `plugin.png` / `plugin@2x.png` | 144 / 288 | 30 / 60 | White grid on a blue (`0.23, 0.51, 0.96`) rounded tile, corner radius 20% of the size |
| `category.png` / `@2x` | 28 / 56 | 4 / 8 | White grid, transparent background |
| `action.png` / `@2x` | 20 / 40 | 2 / 4 | White grid, transparent background |
| `key.png` / `@2x` | 72 / 144 | 20 / 40 | Grid at 55% white, transparent background |

The script writes into the repository's `icons/` folder, whatever the current directory.

---

## 9. Packaging

`build.sh` builds `dist/cloud.caesium.applaunch.sdPlugin.zip`. The zip MUST contain a single top-level folder `cloud.caesium.applaunch.sdPlugin/` holding `manifest.json`, `LICENSE`, `README.md`, `bin/`, `icons/` and `pi/`, and MUST NOT contain `__pycache__`, `applaunch.log`, `debug`, `docs/` (which includes this file), `tools/`, `.git` or `dist/`. Run with `set -euo pipefail`; use a temporary staging folder cleaned up on exit; print the zip's contents.

---

## 10. Out of scope

Encoders and touch strips (only `Keypad`); multiple states; Windows and macOS; editing OpenDeck profile files; any network access; installing applications; per-key shortcuts other than launching an app; automatic refresh of icons when the icon theme changes (see 14.9).

---

## 11. Documents

### 11.1 `README.md`

MUST contain, in this order: title; one-paragraph description; the screenshot (`![…](docs/screenshot.png)`); Features; Requirements (including the OpenDeck 2.14 note and the dependency table for Fedora and Debian/Ubuntu, stating it has been tested only on Fedora); Install (from a release zip, or by cloning into `~/.config/opendeck/plugins/cloud.caesium.applaunch.sdPlugin`, then fully quit and restart OpenDeck); Usage; Label styling table (6.2.4); How it works (search folders, priority, filters; launch method); Troubleshooting (action missing → fully quit OpenDeck; log file; missing app); Development (file table and the start-up command line); Contributing; License.

State in Usage that **changing any option updates the selected key straight away** and that shared options are only defaults.

### 11.2 `LICENSE`

The standard MIT licence text with `Copyright (c) 2026 Caesium Cloud`.

### 11.3 `.gitignore`

```
__pycache__/
applaunch.log
debug
dist/
```

---

## 12. Publishing (reference, not part of the build)

The community catalogue is the repository [OpenActionAPI/plugins](https://github.com/OpenActionAPI/plugins). Submission is a pull request; an automated check then a human review follow.

Before the pull request:

1. A public GitHub repository for the plugin with the topic **`openaction`** and a sidebar description.
2. A GitHub release whose latest release includes a `.zip` (build with `build.sh`).

The pull request changes two things in the catalogue repository:

- `catalogue.json`: add, in the "Native OpenAction plugins" section (sorted alphabetically by repository URL):

  ```json
  "cloud.caesium.applaunch": {
    "name": "App Launch",
    "author": "Caesium Cloud",
    "repository": "https://github.com/<owner>/<repo>",
    "description": "<exactly the repository's sidebar description>",
    "flags": { "ai_assisted": true }
  }
  ```

- `icons/cloud.caesium.applaunch.png`: at least 144×144, a copy of `icons/plugin@2x.png`.

The automated check verifies: the `openaction` topic; `name` and `author` equal the manifest's; the description equals the sidebar description; the key matches the action-UUID prefix; the latest release has a `.zip` or `.streamDeckPlugin`; the icon is a PNG of at least 144×144; the section and alphabetical placement.

The `ai_assisted` flag is set because the plugin was written with an AI assistant.

---

## 13. Automated tests

Run all of these yourself (as the AI) and report each by ID with pass or fail and the evidence. Put test scripts and output images in a scratch directory outside the repository; do not commit them unless asked. Any failure MUST be fixed and the affected tests re-run before moving on.

A passing run shows the plugin built to this spec behaves as the original did when it was developed and tested.

### 13.1 Static checks

| ID | Check | Pass when |
| --- | --- | --- |
| A-01 | `python3 -m py_compile bin/*.py` | No errors |
| A-02 | `node --check pi/pi.js` and `node --check pi/languages.js` | No errors |
| A-03 | `python3 -m json.tool manifest.json` | Valid; `Actions[0].UUID` starts with `cloud.caesium.applaunch.`; `PropertyInspectorPath`, `Icon`, `CategoryIcon` and `CodePathLin` point at files that exist (allowing for the omitted extension and `@2x`) |
| A-04 | `bin/plugin.py` is executable and its first line is `#!/usr/bin/env python3` | True |
| A-05 | Icon files in Section 3 exist with the sizes in Section 8 | `magick identify` agrees |
| A-06 | `git ls-files` (when a repo exists) contains none of `applaunch.log`, `debug`, `__pycache__`, `dist` | True |

### 13.2 Discovery (`apps.py`)

| ID | Check | Pass when |
| --- | --- | --- |
| A-10 | `scan_apps("en")` on a normal desktop | Returns at least 1 app; every item has `id`, `path`, `name`, `exec`, `icon`; names sorted case-insensitively; takes under 0.5 s (the original machine: 56 apps in about 0.03 s) |
| A-11 | `scan_apps("es")` and `scan_apps("de")` | Names differ from `en` for apps with translations; for example `org.gnome.Nautilus` is `Archivos` (es), `Dateien` (de), `Fichiers` (fr) when GNOME Files is installed |
| A-12 | A hidden app (`NoDisplay=true`) and one with a missing `TryExec` are absent | True; test with temporary `.desktop` files in `~/.local/share/applications`, then remove them |
| A-13 | A file in `~/.local/share/applications` with the same desktop ID as a system file | The user's version is returned, once |
| A-14 | Locale fallback for `pt_BR` and `sr_RS@latin` | Tries `Name[pt_BR]` then `Name[pt]` then `Name`; `Name[sr_RS@latin]`, `Name[sr_RS]`, `Name[sr@latin]`, `Name[sr]`, `Name` |
| A-15 | `find_app("no.such.app", "en")` | Returns `None` |

### 13.3 Rendering (`render.py`)

| ID | Check | Pass when |
| --- | --- | --- |
| A-20 | `render_key` returns a valid PNG of exactly 144×144, RGBA | True for every mode with and without a label |
| A-21 | Render `org.gnome.Nautilus` (or any app with an SVG icon) in `full`, `white`, `black`, `custom` (`#10901080`) at scale 80, with and without a label; build a contact sheet on a grey background with `magick montage` and **look at it** | Full colour shows the real icon; white is a white silhouette; black is a black silhouette; custom is a translucent green silhouette; **no icon is blank** (see the `Rsvg.Rectangle` pitfall); the background is transparent |
| A-22 | Label style per Section 6.2.4 | Black mode: black text, no outline. White mode: white text, no outline. Custom: coloured text with a thin black outline. Full: white text with a thin black outline |
| A-23 | A very long name (for example "Btrfs Assistant Very Long Name") | Wraps to at most two lines, fits inside the key, no overlap with the icon |
| A-24 | `scale` 20 and 100 | The icon is visibly smaller at 20; values 5 and 500 are clamped to 20 and 100 |
| A-25 | `parse_color` on `#fff`, `#ffff`, `#10901080`, `10901080`, `zzz`, `None` | Correct floats for valid forms; opaque white for invalid |
| A-26 | An app whose icon is a raster file or an absolute path | Renders (not blank) |
| A-27 | `thumbnail(...)` for all apps | Each starts with `data:image/png;base64,`; whole list in under 1 s; combined size roughly 50 KB |
| A-28 | Every listed app resolves an icon with `resolve_icon_path(icon, 96, False)` | List the ones that do not; there should be none on a typical install (the original machine: none) |

### 13.4 Backend protocol (mock OpenDeck)

Write a small mock OpenDeck in a scratch directory: a TCP server on an ephemeral port that performs the WebSocket handshake (reply `101` with `Sec-WebSocket-Accept` = base64(sha1(key + `258EAFA5-E914-47DA-95CA-C5AB0DC85B11`))), then reads masked client frames and sends unmasked server text frames. Start `bin/plugin.py` with `-port <port> -pluginUUID cloud.caesium.applaunch -registerEvent registerPlugin -info {}`. Use a context such as `sd-X.Default.Keypad.1.2`. Close with a close frame at the end.

| ID | Steps | Pass when |
| --- | --- | --- |
| A-30 | Read the first two messages | `{"event":"registerPlugin","uuid":"cloud.caesium.applaunch"}`, then `{"event":"getGlobalSettings","context":"cloud.caesium.applaunch"}` |
| A-31 | Send `didReceiveGlobalSettings` with `{mode:"full",scale:100}`, then `willAppear` (twice) and `didReceiveSettings` for a key whose settings are `{app, options:{mode:"white",scale:70,renderLabels:false,…}}`; wait 1 s | **The plugin sends no `setImage` and no `setTitle`** (rule R1). Check by waiting for silence. |
| A-32 | Send `sendToPlugin` `hello` for that key | Reply `type:"hello"` with `options` equal to the shared options and `keyOptions` equal to the key's own (white, 70) |
| A-33 | `sendToPlugin` `saveOptions` | The plugin sends `setGlobalSettings` with `context` = plugin UUID, with the options as payload |
| A-34 | `sendToPlugin` `getApps` (`lang:"de"`) | Reply `type:"apps"`; every item has `id`, `path`, `name`, non-empty `thumb`; names are German where translated; reply within 1 s |
| A-35 | `apply` with `org.gnome.Nautilus`, options `{lang:"de",mode:"custom",color:"#10901080",scale:80,renderLabels:true}` | In order: `setSettings`, `setImage` (a PNG data URL), `setTitle` with `""`, then `sendToPropertyInspector` `type:"applied"`. Decode the image and check it is a 144×144 PNG with the label drawn |
| A-36 | `apply` again with only `scale` changed, same app and `renderLabels` | `setSettings`, `setImage`, `applied` — **no `setTitle`** (rule R4). Use the app's real localised name in the previously stored settings, or this test will see a changed name |
| A-37 | `apply` with `renderLabels:false` | `setTitle` with the app's name, and the image has no label |
| A-38 | `apply` with `{id:"no.such.app"}` | Reply `type:"error"` with message `Application 'no.such.app' not found`; no `setImage` |
| A-39 | `keyDown` for a context whose settings have an app that does not exist | `showAlert` for that context (shows the failure path; also writes a `gtk-launch failed` warning to the log) |
| A-40 | After all of the above | `applaunch.log` has no tracebacks; the plugin exits (code 0) when the mock closes the socket |

### 13.5 Settings panel (headless browser)

Serve or open `pi/index.html` (copied to a scratch folder with a test wrapper). Replace `WebSocket` with a stub that records everything sent and answers `hello` and `getApps` with canned data (real app data from the backend is best), then call `connectElgatoStreamDeckSocket(1, 'u', 'registerPropertyInspector', '{}', <actionInfo JSON>)`. Use `--headless=new --virtual-time-budget=… --dump-dom` or `--screenshot`.

| ID | Check | Pass when |
| --- | --- | --- |
| A-50 | Screenshot of the main panel with a configured key (custom mode, `#10901080`, scale 80, language `es`) | All controls from 7.1 are visible; the language box shows `es` with "Español"; the Custom radio is checked, the colour box and swatch are active and the swatch shows translucent green over a checkerboard; the slider reads `80%`; there is **no** "apply when you press OK" text |
| A-51 | Screenshot with the picker open | Overlay with search box, list rows with thumbnails, names and IDs, the key's current app highlighted, status "N of M applications", Cancel and OK |
| A-52 | Change scale, mode and label and the language box; wait 600 ms | Exactly one `saveOptions` then one `apply`, carrying the final values (not one per change) |
| A-53 | The same with a key that has no app | `saveOptions` only; no `apply` |
| A-54 | Custom mode with an invalid colour (`#12`) | No `apply` is sent and the box is marked invalid; **Select Application…** shows an error instead of opening |
| A-55 | `hello` with different shared and key options | Controls show the key's options (rule R2) |
| A-56 | Language box: `pt-br`, `es`, `sr@Latin`, `xx9` | `Português (Brasil)`, `Español`, `Srpski (latinica)`, "Unknown language" |
| A-57 | Picker: type in the search box | The list filters; the count updates |
| A-58 | Picker: select a row and press OK | Sends `apply` with that app's `id` and `path` and the full options |
| A-59 | Picker: Cancel and Escape | Dialog closes; nothing is sent |
| A-5A | Colour box and swatch when a non-Custom radio is selected | Both disabled |

### 13.6 Packaging

| ID | Check | Pass when |
| --- | --- | --- |
| A-60 | Run `./build.sh` | Produces `dist/cloud.caesium.applaunch.sdPlugin.zip` with the contents in Section 9 |
| A-61 | Unzip to a temporary folder | The manifest is valid JSON; the unzipped code finds apps (`apps.scan_apps("en")` runs from the unpacked `bin/`); a recursive diff against the repository shows only the expected differences (excluded files) |

### 13.7 Report

After the automated tests, give the user a table of every test ID with result. State clearly anything skipped and why. Do not claim a test passed unless it ran.

---

## 14. Human tests

These need the real OpenDeck, and ideally a real Stream Deck. Run them **in order**, one at a time. For each: give the user the numbered steps, say exactly what to look for, ask what they saw, and wait. Do not assume the result. If something fails, check `applaunch.log` (create an empty file named `debug` in the plugin folder, ask the user to restart OpenDeck and repeat, then read the log; delete `debug` afterwards).

Before starting: install or copy the plugin into `~/.config/opendeck/plugins/cloud.caesium.applaunch.sdPlugin`, then **ask the user's permission** and have them (or you, with permission) fully quit OpenDeck (tray → Quit) and start it again. Confirm that `Registered plugin cloud.caesium.applaunch.sdPlugin` appears in `~/.local/share/opendeck/logs/opendeck.log`, and that `applaunch.log` shows `registered on port`.

| ID | Steps | Pass when |
| --- | --- | --- |
| H-01 | Open OpenDeck. Look in the actions list. | **App Launch → Launch Application** is listed with its grid icon |
| H-02 | Drag it onto an empty key. | The key shows the translucent nine-dot grid; the settings panel opens |
| H-03 | Press **Select Application…**. | The picker opens with thumbnails; typing filters the list |
| H-04 | Pick an app (such as Files) and press **OK**. | The key shows the app's icon and name; the panel shows the app |
| H-05 | Press the key on the deck. | The application launches (a second press behaves as the app normally does) |
| H-06 | Change **Icon colour** to White, then Black, then Custom (`#10901080`), then back to Full colour. | The key updates **immediately** each time, with the label colours in the table in 6.2.4 |
| H-07 | Move the **Image scale** slider. | The icon resizes on the key as you let go; the label is unchanged |
| H-08 | Switch **Label** between "Render into image" and "Set as key title". | The name moves between the image and OpenDeck's own text |
| H-09 | Change **Language** to `de`, `fr`, `es`. | The language's own name appears beside the box; the key's name changes where the app has a translation |
| H-10 | Add a second and a third Launch Application key, choosing a different app on each. | Earlier keys **keep** their icons. (On OpenDeck 2.12.1 they revert to the grid; that is OpenDeck's bug, not the plugin's — upgrade to 2.14 or later.) |
| H-11 | Give key A scale 100 and key B scale 60 and a different colour mode. Select key A, then key B. | Each key's panel shows **its own** settings (rule R2) |
| H-12 | On key B, change only the scale. | Key A and key C are untouched; key B's colour mode is unchanged (rules R2, R3) |
| H-13 | In OpenDeck's own key editor, change a key's title text, then change only that key's scale in the plugin panel. | The edited title text is **kept** (rule R4) |
| H-14 | Quit OpenDeck from the tray, start it again. | **Every key looks exactly as it did before**: icon, scale, text (rule R1) |
| H-15 | Press a key whose app is not installed (uninstall one, or edit settings) | The key shows OpenDeck's red alert image briefly |
| H-16 | Clean install check: build the zip, remove the plugin folder, unzip the release zip into `~/.config/opendeck/plugins/`, restart OpenDeck. | The plugin loads and works as H-01 to H-05 |

After H-16, tell the user which tests passed and which did not, and offer to continue with Section 12 (publishing). **Do not commit, push, create a GitHub repository, open a pull request, or restart OpenDeck without being asked.**

---

## 15. Changing the plugin

| If you want to… | Change | Re-run |
| --- | --- | --- |
| Add an option (for example a font) | Section 5.2 table; `render.py`; `pi/` controls; `README.md` | A-20 to A-24, A-52, A-55; H-06 to H-14 |
| Support a new `.desktop` folder or filter | 6.1.1 or 6.1.2; `apps.py`; README "How it works" | A-10 to A-15 |
| Change label colours or outline | Table in 6.2.4 and `LABEL_STYLE`; README table | A-21, A-22; H-06 |
| Add a language | Appendix A and `pi/languages.js` | A-56 |
| Change the launch method | 6.3.5 and `Plugin.launch` | A-39; H-05, H-15 |
| Add another action (for example a folder opener) | New entry in `manifest.json`; a new `action` UUID; handlers in `plugin.py`; **update rule R1 if it paints** | A-03, A-30 to A-40, H-01 |
| Change the key size | `KEY_SIZE`; D7 | A-20, A-21 |

Whenever behaviour changes, update the text here first, then the code, then the test table, so this file stays the single source of truth.

---

## 16. Known limitations

- **OpenDeck 2.12.1** resets other keys' icons when a new action is added (fixed in 2.14.0).
- **Tested on Fedora only.** Other distributions need equivalent packages (see README); the Debian/Ubuntu names were not tried.
- **Icons do not refresh automatically** when the icon theme or an app's icon changes, because R1 forbids background repainting. Changing any option on a key (or choosing the app again) refreshes it.
- **Single-colour modes** use the app's `-symbolic` icon when one exists; otherwise the full-colour icon is turned into a flat silhouette, which can look like a blob for icons with large filled shapes.
- **Shared options** are saved by the backend; the panel assumes OpenDeck forwards `setGlobalSettings` and returns `didReceiveGlobalSettings`. If it does not, per-key options still work and only the starting values for new keys are lost.
- **Keypad only** (no dials or touch strips).
- The panel's visual behaviour was verified in a headless Chromium browser, not in OpenDeck's own web view; H-02 to H-09 cover that gap.

---

## Appendix A — Language codes

The panel's language table (`pi/languages.js`). Each code is the suffix of `Name[xx]` keys in `.desktop` files; the value is the language's own name, shown beside the language box.

| Code | Name |
| --- | --- |
| `af` | Afrikaans |
| `an` | Aragonés |
| `ar` | العربية |
| `as` | অসমীয়া |
| `ast` | Asturianu |
| `be` | Беларуская |
| `bg` | Български |
| `bn` | বাংলা |
| `bn_IN` | বাংলা (ভারত) |
| `bs` | Bosanski |
| `ca` | Català |
| `ca@valencia` | Català (Valencià) |
| `ckb` | کوردیی ناوەندی |
| `crh` | Qırımtatarca |
| `cs` | Čeština |
| `da` | Dansk |
| `de` | Deutsch |
| `el` | Ελληνικά |
| `en` | English |
| `en_CA` | English (Canada) |
| `en_GB` | English (United Kingdom) |
| `en_US` | English (United States) |
| `eo` | Esperanto |
| `es` | Español |
| `et` | Eesti |
| `eu` | Euskara |
| `fa` | فارسی |
| `fi` | Suomi |
| `fo` | Føroyskt |
| `fr` | Français |
| `fur` | Furlan |
| `ga` | Gaeilge |
| `gd` | Gàidhlig |
| `gl` | Galego |
| `gu` | ગુજરાતી |
| `he` | עברית |
| `hi` | हिन्दी |
| `hr` | Hrvatski |
| `hu` | Magyar |
| `ia` | Interlingua |
| `id` | Bahasa Indonesia |
| `ie` | Interlingue |
| `is` | Íslenska |
| `it` | Italiano |
| `ja` | 日本語 |
| `ka` | ქართული |
| `kab` | Taqbaylit |
| `kk` | Қазақ тілі |
| `kn` | ಕನ್ನಡ |
| `ko` | 한국어 |
| `ky` | Кыргызча |
| `ln` | Lingála |
| `lo` | ລາວ |
| `lt` | Lietuvių |
| `lv` | Latviešu |
| `mjw` | Karbi |
| `mk` | Македонски |
| `ml` | മലയാളം |
| `mr` | मराठी |
| `ms` | Bahasa Melayu |
| `my` | မြန်မာ |
| `nb` | Norsk bokmål |
| `ne` | नेपाली |
| `nl` | Nederlands |
| `nn` | Norsk nynorsk |
| `oc` | Occitan |
| `or` | ଓଡ଼ିଆ |
| `pa` | ਪੰਜਾਬੀ |
| `pl` | Polski |
| `pt` | Português |
| `pt_BR` | Português (Brasil) |
| `ro` | Română |
| `ru` | Русский |
| `sk` | Slovenčina |
| `sl` | Slovenščina |
| `sr` | Српски |
| `sr@latin` | Srpski (latinica) |
| `sv` | Svenska |
| `ta` | தமிழ் |
| `te` | తెలుగు |
| `tg` | Тоҷикӣ |
| `th` | ไทย |
| `tr` | Türkçe |
| `ug` | ئۇيغۇرچە |
| `uk` | Українська |
| `uz` | Oʻzbekcha |
| `vi` | Tiếng Việt |
| `zh_CN` | 中文（简体） |
| `zh_HK` | 中文（香港） |
| `zh_TW` | 中文（繁體） |

`en_US` is included so the system language `en_US` displays as "English (United States)".

---

## Appendix B — Message reference

Messages between the three parties use the Elgato Stream Deck plugin protocol.

**OpenDeck → backend:** `willAppear`, `willDisappear`, `didReceiveSettings`, `didReceiveGlobalSettings`, `keyDown`, `sendToPlugin`, and others that are ignored (`deviceDidConnect`, `titleParametersDidChange`, `propertyInspectorDidAppear`, `propertyInspectorDidDisappear`).

**Backend → OpenDeck** (all carry `context`; all except `setGlobalSettings` also carry `action`):

| Event | Payload |
| --- | --- |
| `setImage` | `{"image": "data:image/png;base64,…", "target": 0}` |
| `setTitle` | `{"title": "<text>", "target": 0}` |
| `setSettings` | the key's settings object (5.1) |
| `setGlobalSettings` | the shared options object (5.3); `context` is the plugin UUID |
| `showAlert` | none |
| `sendToPropertyInspector` | `hello`, `apps`, `applied` or `error` reply (6.3.4) |

**Panel → OpenDeck:** `registerPropertyInspector` (once), then `sendToPlugin` requests (6.3.4).

**OpenDeck → panel:** `sendToPropertyInspector` (replies), `didReceiveSettings`.
