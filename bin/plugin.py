#!/usr/bin/env python3
"""OpenDeck / Stream Deck plugin: launch desktop applications from keys.

Started by OpenDeck as:
    plugin.py -port N -pluginUUID UUID -registerEvent EVENT -info JSON
"""

import base64
import json
import logging
import os
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import apps  # noqa: E402
import render  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent.parent
ACTION_UUID = "cloud.caesium.applaunch.launch"

logging.basicConfig(
    filename=PLUGIN_DIR / "applaunch.log",
    filemode="w",
    level=logging.DEBUG if os.environ.get("APPLAUNCH_DEBUG") or (PLUGIN_DIR / "debug").exists() else logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("applaunch")


class WebSocket:
    """Minimal RFC 6455 client (text frames, ping/pong) using only the stdlib."""

    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port))
        self.send_lock = threading.Lock()
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("connection closed during handshake")
            response += chunk
        header, _, self.buffer = response.partition(b"\r\n\r\n")
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"handshake failed: {header[:200]!r}")

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _send_frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        # XOR the whole payload at once via big integers (fast for large frames).
        repeated = (mask * (n // 4 + 1))[:n]
        masked = (int.from_bytes(payload, "big") ^ int.from_bytes(repeated, "big")).to_bytes(n, "big") if n else b""
        with self.send_lock:
            self.sock.sendall(header + mask + masked)

    def send(self, obj):
        self._send_frame(0x1, json.dumps(obj).encode())

    def recv(self):
        """Return the next text message as a str, or None when the socket closes."""
        message = b""
        while True:
            b0, b1 = self._read(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            message += payload
            if fin:
                return message.decode("utf-8", errors="replace")


class Plugin:
    def __init__(self, ws, plugin_uuid):
        self.ws = ws
        self.plugin_uuid = plugin_uuid
        self.settings = {}  # context -> button settings
        self.options = {}  # shared PI options, kept in OpenDeck's global settings

    # ---- outbound -------------------------------------------------------

    def send(self, event, context, payload=None, action=ACTION_UUID):
        msg = {"event": event, "context": context}
        if action:
            msg["action"] = action
        log.debug("-> %s %s", event, context)
        if payload is not None:
            msg["payload"] = payload
        self.ws.send(msg)

    def to_pi(self, context, payload):
        self.send("sendToPropertyInspector", context, payload)

    # ---- key appearance -------------------------------------------------

    def paint(self, context, settings, set_title=True):
        """Draw a configured key from its stored settings.

        Only called for an explicit change (an app chosen or an option edited
        for this key). OpenDeck persists the image and title it was given, so
        startup and other events must never repaint.
        """
        app = settings.get("app")
        opts = settings.get("options", {})
        if not app:
            return
        render_labels = bool(opts.get("renderLabels", True))
        png = render.render_key(
            app.get("icon"), opts.get("mode", "full"), opts.get("color"),
            opts.get("scale", 100), app.get("name") if render_labels else None,
        )
        self.send("setImage", context, {"image": render.data_url(png), "target": 0})
        if set_title:
            self.send("setTitle", context, {"title": "" if render_labels else app.get("name", ""), "target": 0})

    def key_thumbnail(self, settings):
        """Small preview of a configured key for the property inspector."""
        app = settings.get("app")
        if not app:
            return ""
        opts = settings.get("options", {})
        return render.thumbnail(app.get("icon"), opts.get("mode", "full"), opts.get("color"))

    # ---- requests from the property inspector ---------------------------

    def handle_pi(self, context, payload):
        request = payload.get("request")
        if request == "hello":
            self.to_pi(context, {
                "type": "hello",
                "systemLanguage": apps.system_language(),
                "options": self.options,
                "keyOptions": self.settings.get(context, {}).get("options"),
                "thumb": self.key_thumbnail(self.settings.get(context, {})),
            })
        elif request == "saveOptions":
            self.options = payload.get("options") or {}
            self.send("setGlobalSettings", self.plugin_uuid, self.options, action=None)
        elif request == "getApps":
            lang = payload.get("lang") or apps.system_language()
            mode, color = payload.get("mode", "full"), payload.get("color")
            result = []
            for app in apps.scan_apps(lang):
                try:
                    thumb = render.thumbnail(app["icon"], mode, color)
                except Exception:
                    log.exception("thumbnail failed for %s", app["id"])
                    thumb = ""
                result.append({"id": app["id"], "path": app["path"], "name": app["name"], "thumb": thumb})
            log.info("sending %d apps (lang=%s mode=%s)", len(result), lang, mode)
            self.to_pi(context, {"type": "apps", "apps": result})
        elif request == "apply":
            opts = payload.get("options", {})
            lang = opts.get("lang") or apps.system_language()
            chosen = payload.get("app") or {}
            app = apps.find_app(chosen.get("id"), lang, chosen.get("path"))
            if not app:
                self.to_pi(context, {"type": "error", "message": f"Application {chosen.get('id')!r} not found"})
                return
            settings = {"app": app, "options": opts}
            previous = self.settings.get(context, {})
            # Leave the title alone unless what it shows has changed, so text
            # edited in OpenDeck survives e.g. a scale or colour change.
            title_changed = (
                previous.get("app", {}).get("id") != app["id"]
                or previous.get("app", {}).get("name") != app["name"]
                or previous.get("options", {}).get("renderLabels", True) != opts.get("renderLabels", True)
            )
            self.settings[context] = settings
            self.send("setSettings", context, settings)
            self.paint(context, settings, set_title=title_changed)
            self.to_pi(context, {"type": "applied", "settings": settings, "thumb": self.key_thumbnail(settings)})
            log.info("configured %s -> %s", context, app["id"])

    # ---- launching ------------------------------------------------------

    def launch(self, context, settings):
        app = settings.get("app")
        if not app:
            self.send("showAlert", context)
            return
        env = os.environ.copy()
        dirs = [d for d in env.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if d]
        for extra in (str(Path.home() / ".local/share/flatpak/exports/share"), "/var/lib/flatpak/exports/share"):
            if extra not in dirs:
                dirs.append(extra)
        env["XDG_DATA_DIRS"] = ":".join(dirs)
        quiet = {"env": env, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                 "stderr": subprocess.DEVNULL, "start_new_session": True}
        try:
            if subprocess.run(["gtk-launch", app["id"]], timeout=15, **quiet).returncode == 0:
                log.info("launched %s with gtk-launch", app["id"])
                return
            log.warning("gtk-launch failed for %s, trying gio launch", app["id"])
            if app.get("path") and subprocess.run(["gio", "launch", app["path"]], timeout=15, **quiet).returncode == 0:
                log.info("launched %s with gio launch", app["path"])
                return
        except (OSError, subprocess.TimeoutExpired):
            log.exception("launch failed for %s", app["id"])
        self.send("showAlert", context)

    # ---- event loop -----------------------------------------------------

    def dispatch(self, msg):
        event = msg.get("event")
        context = msg.get("context")
        log.debug("<- %s %s", event, context)
        payload = msg.get("payload") or {}
        if event in ("willAppear", "didReceiveSettings"):
            settings = payload.get("settings") or {}
            self.settings[context] = settings
        elif event == "didReceiveGlobalSettings":
            self.options = payload.get("settings") or {}
        elif event == "willDisappear":
            self.settings.pop(context, None)
        elif event == "keyDown":
            settings = payload.get("settings") or self.settings.get(context, {})
            threading.Thread(target=self.launch, args=(context, settings), daemon=True).start()
        elif event == "sendToPlugin":
            # Heavy work (scan + render) runs off the read loop.
            threading.Thread(target=self.safe_pi, args=(context, payload), daemon=True).start()

    def safe_pi(self, context, payload):
        try:
            self.handle_pi(context, payload)
        except Exception as exc:
            log.exception("property inspector request failed")
            self.to_pi(context, {"type": "error", "message": str(exc)})

    def run(self):
        while True:
            raw = self.ws.recv()
            if raw is None:
                log.info("socket closed, exiting")
                return
            try:
                self.dispatch(json.loads(raw))
            except Exception:
                log.exception("failed to handle message: %.300s", raw)


def main(argv):
    args = dict(zip(argv[1::2], argv[2::2]))
    port = int(args["-port"])
    ws = WebSocket("127.0.0.1", port)
    ws.send({"event": args["-registerEvent"], "uuid": args["-pluginUUID"]})
    ws.send({"event": "getGlobalSettings", "context": args["-pluginUUID"]})
    log.info("registered on port %d", port)
    Plugin(ws, args["-pluginUUID"]).run()


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        log.exception("fatal")
        raise
