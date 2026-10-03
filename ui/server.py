#!/usr/bin/env python3
"""Room EQ UI: a touchscreen / phone remote for CamillaDSP.

Talks to CamillaDSP's websocket (port 1234), serves the web page, and pushes
live levels and status to every connected screen.
Requires: sudo apt install python3-aiohttp python3-yaml
"""
import asyncio
import copy
import json
import os
import shutil
import time
from pathlib import Path

import yaml
from aiohttp import web, ClientSession, WSMsgType

CAMILLA_URL = os.environ.get("CAMILLA_URL", "ws://127.0.0.1:1234")
PORT = int(os.environ.get("ROOMEQ_PORT", "8080"))
CONFIG_DIR = Path(os.environ.get("CAMILLA_CONFIG_DIR", "~/camilladsp/configs")).expanduser()
DATA_DIR = Path(os.environ.get("ROOMEQ_DATA_DIR", "~/camilladsp/roomeq_ui")).expanduser()
UPLOAD_DIR = DATA_DIR / "uploads"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATIC_DIR = Path(__file__).resolve().parent
LOWCUT_NAME = "__roomeq_lowcut"
LEVEL_INTERVAL = 0.07   # seconds between level updates (~14 per second)
STATUS_INTERVAL = 1.0

DEFAULT_SETTINGS = {
    "background": "carbon",      # carbon | plain | walnut | custom
    "background_file": None,
    "logo_file": None,
    "opacity": 0.9,
    "lowcut_freq": 80,
    "disabled": {},              # config path -> list of filter names switched off
}


class Camilla:
    """Minimal request/response client for CamillaDSP's websocket API."""

    def __init__(self, url):
        self.url = url
        self.session = None
        self.ws = None
        self.lock = asyncio.Lock()

    async def _connect(self):
        if self.session is None:
            self.session = ClientSession()
        self.ws = await self.session.ws_connect(self.url, max_msg_size=0)

    async def call(self, command, arg=None):
        """Send one command; returns its value. Raises RuntimeError on failure."""
        msg = command if arg is None else {command: arg}
        async with self.lock:
            for attempt in (1, 2):
                try:
                    if self.ws is None or self.ws.closed:
                        await self._connect()
                    await self.ws.send_str(json.dumps(msg))
                    reply = await asyncio.wait_for(self.ws.receive(), timeout=3)
                    if reply.type != WSMsgType.TEXT:
                        raise ConnectionError("connection closed")
                    data = json.loads(reply.data)
                    break
                except (OSError, ConnectionError, asyncio.TimeoutError, Exception) as exc:
                    if self.ws is not None:
                        await self.ws.close()
                    self.ws = None
                    if attempt == 2:
                        raise RuntimeError(f"CamillaDSP not reachable: {exc}")
        key = next(iter(data))
        body = data[key]
        if key == "Invalid":
            raise RuntimeError(body.get("error", "invalid command"))
        if body.get("result") != "Ok":
            raise RuntimeError(f"{command}: {body.get('result')} {body.get('value', '')}".strip())
        return body.get("value")


class App:
    def __init__(self):
        self.cdsp = Camilla(CAMILLA_URL)
        self.clients = set()
        self.settings = self._load_settings()
        self.config_path = None
        self.base = None            # config as saved/edited by the user (no app additions)
        self.bypass = False
        self.lowcut = False
        self.dirty = False
        self.history = []
        self._last_undo_key = None
        self._last_undo_time = 0
        self._apply_task = None
        self.status = {}
        self.signal_levels_cmd = True
        self.error = None

    # ---------- settings ----------
    def _load_settings(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        s = dict(DEFAULT_SETTINGS)
        try:
            s.update(json.loads(SETTINGS_FILE.read_text()))
        except (OSError, ValueError):
            pass
        return s

    def save_settings(self):
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, indent=2))
        tmp.replace(SETTINGS_FILE)

    def disabled(self):
        return set(self.settings["disabled"].get(str(self.config_path), []))

    def set_disabled(self, names):
        self.settings["disabled"][str(self.config_path)] = sorted(names)
        self.save_settings()

    # ---------- config handling ----------
    async def load_active(self):
        """Read the active config file from CamillaDSP and load it."""
        try:
            path = await self.cdsp.call("GetConfigFilePath")
        except RuntimeError as exc:
            self.error = str(exc)
            return
        if path and Path(path).exists():
            self.config_path = Path(path)
            self.base = yaml.safe_load(Path(path).read_text())
        else:
            raw = await self.cdsp.call("GetConfigJson")
            self.base = json.loads(raw) if raw else None
            self.config_path = Path(path) if path else None
        self.dirty = False
        self.history.clear()
        self.error = None

    def effective(self):
        """Config actually sent to CamillaDSP: base plus bypass, low cut and switched-off filters."""
        cfg = copy.deepcopy(self.base)
        if cfg is None:
            return None
        off = self.disabled()
        steps = []
        for step in cfg.get("pipeline") or []:
            if step.get("type") == "Filter":
                if self.bypass:
                    continue
                names = [n for n in step.get("names", []) if n not in off]
                if not names:
                    continue
                step = dict(step, names=names)
            steps.append(step)
        if self.lowcut and not self.bypass:
            cfg.setdefault("filters", {})[LOWCUT_NAME] = {
                "type": "BiquadCombo",
                "parameters": {"type": "ButterworthHighpass",
                               "freq": float(self.settings["lowcut_freq"]), "order": 4},
            }
            chans = self._channels(cfg)
            lc = {"type": "Filter", "names": [LOWCUT_NAME]}
            if chans is not None:
                lc["channels"] = chans
            steps.insert(0, lc)
        cfg["pipeline"] = steps
        return cfg

    def _channels(self, cfg):
        for step in self.base.get("pipeline") or []:
            if step.get("type") == "Filter" and step.get("channels") is not None:
                return list(step["channels"])
        try:
            return list(range(int(cfg["devices"]["capture"]["channels"])))
        except (KeyError, TypeError, ValueError):
            return None

    def schedule_apply(self, delay=0.04):
        if self._apply_task and not self._apply_task.done():
            self._apply_task.cancel()
        self._apply_task = asyncio.ensure_future(self._apply_later(delay))

    async def _apply_later(self, delay):
        try:
            await asyncio.sleep(delay)
            await self.apply()
        except asyncio.CancelledError:
            pass

    async def apply(self):
        cfg = self.effective()
        if cfg is None:
            return
        try:
            await self.cdsp.call("SetConfigJson", json.dumps(cfg))
            self.error = None
        except RuntimeError as exc:
            self.error = str(exc)
        await self.broadcast_state()

    def push_undo(self, key=None):
        now = time.monotonic()
        if key is not None and key == self._last_undo_key and now - self._last_undo_time < 1.5:
            self._last_undo_time = now
            return
        self._last_undo_key, self._last_undo_time = key, now
        self.history.append((copy.deepcopy(self.base), sorted(self.disabled())))
        del self.history[:-60]

    # ---------- model sent to the screens ----------
    def model(self):
        filters, seen = [], set()
        base = self.base or {}
        off = self.disabled()
        for step in base.get("pipeline") or []:
            if step.get("type") != "Filter":
                continue
            for name in step.get("names", []):
                if name in seen or name not in (base.get("filters") or {}):
                    continue
                seen.add(name)
                f = base["filters"][name]
                filters.append({"name": name, "type": f.get("type"),
                                "parameters": f.get("parameters", {}),
                                "enabled": name not in off})
        presets = sorted(p.name for p in CONFIG_DIR.glob("*.y*ml")) if CONFIG_DIR.exists() else []
        try:
            samplerate = int(base.get("devices", {}).get("samplerate", 48000))
        except (TypeError, ValueError):
            samplerate = 48000
        return {
            "type": "state",
            "config_name": self.config_path.name if self.config_path else None,
            "presets": presets,
            "filters": filters,
            "samplerate": samplerate,
            "bypass": self.bypass,
            "lowcut": self.lowcut,
            "lowcut_freq": self.settings["lowcut_freq"],
            "dirty": self.dirty,
            "can_undo": bool(self.history),
            "settings": {k: self.settings[k] for k in
                         ("background", "background_file", "logo_file", "opacity")},
            "error": self.error,
        }

    async def broadcast(self, payload):
        text = json.dumps(payload)
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except (ConnectionError, RuntimeError):
                self.clients.discard(ws)

    async def broadcast_state(self):
        await self.broadcast(self.model())

    # ---------- commands from the screens ----------
    async def handle(self, msg):
        cmd = msg.get("cmd")
        if self.base is None and cmd not in ("settings", "preset"):
            await self.load_active()
        if cmd == "set_param":
            name, param, value = msg["name"], msg["param"], msg["value"]
            f = self.base["filters"].get(name)
            if f is None:
                return
            self.push_undo((name, param))
            f.setdefault("parameters", {})[param] = round(float(value), 3)
            self.dirty = True
            self.schedule_apply()
        elif cmd == "toggle_filter":
            self.push_undo()
            off = self.disabled()
            off.symmetric_difference_update({msg["name"]})
            self.set_disabled(off)
            self.schedule_apply(0)
        elif cmd == "add_band":
            self.push_undo()
            filters = self.base.setdefault("filters", {})
            i = 1
            while f"band {i}" in filters:
                i += 1
            name = f"band {i}"
            filters[name] = {"type": "Biquad", "parameters":
                             {"type": "Peaking", "freq": float(msg.get("freq", 1000)),
                              "gain": 0.0, "q": 1.41}}
            pipe = self.base.setdefault("pipeline", [])
            step = next((s for s in pipe if s.get("type") == "Filter"), None)
            if step is None:
                step = {"type": "Filter", "names": []}
                chans = self._channels(self.base)
                if chans is not None:
                    step["channels"] = chans
                pipe.append(step)
            step.setdefault("names", []).append(name)
            self.dirty = True
            await self.apply()
            await self.broadcast({"type": "selected", "name": name})
        elif cmd == "remove_filter":
            name = msg["name"]
            self.push_undo()
            for step in self.base.get("pipeline") or []:
                if step.get("type") == "Filter" and name in step.get("names", []):
                    step["names"] = [n for n in step["names"] if n != name]
            self.base["pipeline"] = [s for s in self.base.get("pipeline") or []
                                     if s.get("type") != "Filter" or s.get("names")]
            (self.base.get("filters") or {}).pop(name, None)
            self.dirty = True
            await self.apply()
        elif cmd == "set_mode":
            mode = msg["mode"]
            self.bypass = mode == "flat"
            if mode == "night":
                self.lowcut = True
            elif mode == "room":
                self.lowcut = False
            await self.apply()
        elif cmd == "set_bypass":
            self.bypass = bool(msg["value"])
            await self.apply()
        elif cmd == "set_lowcut":
            self.lowcut = bool(msg["value"])
            await self.apply()
        elif cmd == "preset":
            name = Path(msg["name"]).name
            path = CONFIG_DIR / name
            if not path.exists():
                return
            try:
                await self.cdsp.call("SetConfigFilePath", str(path))
            except RuntimeError as exc:
                self.error = str(exc)
            self.config_path = path
            self.base = yaml.safe_load(path.read_text())
            self.dirty = False
            self.history.clear()
            await self.apply()
        elif cmd == "save":
            await self.save()
        elif cmd == "undo":
            if self.history:
                self.base, off = self.history.pop()
                self.set_disabled(off)
                self._last_undo_key = None
                self.dirty = True
                await self.apply()
        elif cmd == "settings":
            for k in ("background", "opacity", "logo_file", "background_file"):
                if k in msg.get("values", {}):
                    self.settings[k] = msg["values"][k]
            self.save_settings()
            await self.broadcast_state()

    async def save(self):
        if self.config_path is None or self.base is None:
            self.error = "No config file to save to"
        else:
            backup = self.config_path.with_suffix(self.config_path.suffix + ".bak")
            if self.config_path.exists():
                shutil.copy2(self.config_path, backup)
            tmp = self.config_path.with_suffix(".tmp")
            tmp.write_text(yaml.safe_dump(self.base, sort_keys=False, allow_unicode=True))
            tmp.replace(self.config_path)
            self.dirty = False
            self.error = None
        await self.broadcast_state()

    # ---------- background loops ----------
    async def level_loop(self):
        while True:
            await asyncio.sleep(LEVEL_INTERVAL)
            if not self.clients:
                continue
            try:
                if self.signal_levels_cmd:
                    try:
                        lv = await self.cdsp.call("GetSignalLevels")
                        levels = {k: lv.get(k, []) for k in
                                  ("capture_peak", "capture_rms", "playback_peak", "playback_rms")}
                    except RuntimeError as exc:
                        if "not reachable" in str(exc):
                            raise
                        self.signal_levels_cmd = False
                        continue
                else:
                    levels = {
                        "capture_peak": await self.cdsp.call("GetCaptureSignalPeak"),
                        "capture_rms": await self.cdsp.call("GetCaptureSignalRms"),
                        "playback_peak": await self.cdsp.call("GetPlaybackSignalPeak"),
                        "playback_rms": await self.cdsp.call("GetPlaybackSignalRms"),
                    }
                await self.broadcast({"type": "levels", **levels})
            except RuntimeError:
                await asyncio.sleep(1)

    async def status_loop(self):
        while True:
            st = {"type": "status"}
            for key, cmd in (("state", "GetState"), ("load", "GetProcessingLoad"),
                             ("capture_rate", "GetCaptureRate"), ("clipped", "GetClippedSamples"),
                             ("rate_adjust", "GetRateAdjust")):
                try:
                    st[key] = await self.cdsp.call(cmd)
                except RuntimeError:
                    st[key] = None
            try:
                st["temp"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
            except (OSError, ValueError):
                st["temp"] = None
            if self.base is None and st["state"] is not None:
                await self.load_active()
                await self.broadcast_state()
            self.status = st
            if self.clients:
                await self.broadcast(st)
            await asyncio.sleep(STATUS_INTERVAL)


app_state = App()


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    app_state.clients.add(ws)
    if app_state.base is None:
        await app_state.load_active()
    await ws.send_str(json.dumps(app_state.model()))
    if app_state.status:
        await ws.send_str(json.dumps(app_state.status))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    await app_state.handle(json.loads(msg.data))
                except Exception as exc:  # report, keep the connection alive
                    app_state.error = f"{type(exc).__name__}: {exc}"
                    await app_state.broadcast_state()
    finally:
        app_state.clients.discard(ws)
    return ws


async def upload_handler(request):
    kind = request.match_info["kind"]
    if kind not in ("logo", "background"):
        raise web.HTTPNotFound()
    reader = await request.multipart()
    field = await reader.next()
    if field is None or not field.filename:
        raise web.HTTPBadRequest(text="No file")
    ext = Path(field.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        raise web.HTTPBadRequest(text="Use a PNG, JPG, WebP, GIF or SVG image")
    name = f"{kind}-{int(time.time())}{ext}"
    with open(UPLOAD_DIR / name, "wb") as out:
        while chunk := await field.read_chunk():
            out.write(chunk)
    old = app_state.settings.get(f"{kind}_file")
    app_state.settings[f"{kind}_file"] = name
    if kind == "background":
        app_state.settings["background"] = "custom"
    app_state.save_settings()
    if old and old != name:
        (UPLOAD_DIR / old).unlink(missing_ok=True)
    await app_state.broadcast_state()
    return web.json_response({"file": name})


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def on_startup(app):
    app["tasks"] = [asyncio.ensure_future(app_state.level_loop()),
                    asyncio.ensure_future(app_state.status_loop())]


def main():
    app = web.Application(client_max_size=20 * 1024 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/upload/{kind}", upload_handler)
    app.router.add_static("/uploads/", UPLOAD_DIR)
    app.router.add_get("/manifest.json", lambda r: web.FileResponse(STATIC_DIR / "manifest.json"))
    app.router.add_get("/icon.svg", lambda r: web.FileResponse(STATIC_DIR / "icon.svg"))
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
