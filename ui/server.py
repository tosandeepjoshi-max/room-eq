#!/usr/bin/env python3
"""Room EQ UI: a touchscreen / phone remote for CamillaDSP.

Talks to CamillaDSP's websocket (port 1234), serves the web page, and pushes
live levels and status to every connected screen.
Requires: sudo apt install python3-aiohttp python3-yaml
"""
import asyncio
import copy
import json
import math
import os
import re
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
MODES = ("room", "flat", "night", "vocal")
# Vocal and Night are tone-fader settings: switching mode moves the tone faders, and each mode
# remembers its own adjustments in settings.json ("mode_tones"). Room EQ uses the preset's own values.
# Tone faders are the gain filters not named "room ..." (room correction) and not the preamp.
# Vocal: speech range lifted, low end trimmed. Night: deep bass and top treble cut, plus a compressor.
DEFAULT_MODE_TONES = {
    # Vocal (2026-10-04, from dialogue-EQ guidance): rumble down, mud (200-500 Hz) cut 1-2 dB,
    # presence 2-4 kHz +2.5-3 dB; 125 Hz kept near 0 so male voices stay full.
    "vocal": {"31 Hz": -6.0, "63 Hz": -4.0, "125 Hz": -1.0, "250 Hz": -2.0, "500 Hz": -1.0,
              "1 kHz": 0.0, "2 kHz": 3.0, "4 kHz": 2.5, "8 kHz": 0.0, "16 kHz": 0.0},
    # Night: deep bass cut hard (carries through walls), slight dialogue lift, sharp highs softened;
    # the compressor does most of the work.
    "night": {"31 Hz": -12.0, "63 Hz": -6.0, "125 Hz": -2.0, "250 Hz": -1.0, "500 Hz": 0.0,
              "1 kHz": 0.0, "2 kHz": 2.0, "4 kHz": 1.0, "8 kHz": -2.0, "16 kHz": -4.0},
}
NIGHT_COMPRESSOR = {"type": "Compressor", "parameters": {
    "channels": 2, "attack": 0.01, "release": 0.6, "threshold": -35.0, "factor": 4.0,
    "makeup_gain": 8.0, "soft_clip": True, "monitor_channels": [0, 1], "process_channels": [0, 1]}}
# Touchscreen backlight; writable by the video group, so no sudo is needed.
BACKLIGHT_DIR = os.environ.get("ROOMEQ_BACKLIGHT") or next(iter(sorted(Path("/sys/class/backlight").glob("*"))), None)
SLEEP_CHOICES = (0, 1, 2, 5, 10, 15, 30, 60)   # minutes; 0 = never
# Resets the USB gadget link to the Shield (stop camilladsp, reload g_audio, start camilladsp).
# Needs a root-owned /usr/local/bin/roomeq-reconnect and a sudoers rule allowing it without a password.
RECONNECT_CMD = ["sudo", "-n", "/usr/local/bin/roomeq-reconnect"]
LEVEL_INTERVAL = 0.07   # seconds between level updates (~14 per second)
STATUS_INTERVAL = 1.0

DEFAULT_SETTINGS = {
    "background": "carbon",      # carbon | plain | walnut | custom
    "background_file": None,
    "logo_file": None,
    "opacity": 0.9,
    "auto_preamp": True,         # preamp follows the largest boost so boosts never clip
    "lowcut_freq": 80,
    "brightness": 100,           # touchscreen backlight, percent (10-100)
    "sleep_minutes": 5,          # touchscreen goes dark after this idle time; 0 = never
    "disabled": {},              # config path -> list of filter names switched off
    "mode_tones": copy.deepcopy(DEFAULT_MODE_TONES),   # mode -> {tone fader name: gain dB}
}


def _biquad_coefs(kind, p, fs):
    """RBJ cookbook coefficients (b0, b1, b2, a0, a1, a2), as CamillaDSP computes them."""
    w = 2 * math.pi * p["freq"] / fs
    cw, sw = math.cos(w), math.sin(w)
    a = 10 ** ((p.get("gain") or 0) / 40)
    if kind == "Peaking":
        alpha = sw / (2 * p["q"]) if p.get("q") else sw * math.sinh(math.log(2) / 2 * (p.get("bandwidth") or 1) * w / sw)
        return (1 + alpha * a, -2 * cw, 1 - alpha * a, 1 + alpha / a, -2 * cw, 1 - alpha / a)
    if kind in ("Lowshelf", "Highshelf"):
        if p.get("q"):
            alpha = sw / (2 * p["q"])
        else:
            s = (p.get("slope") or 6) / 12
            alpha = sw / 2 * math.sqrt((a + 1 / a) * (1 / s - 1) + 2)
        sa = 2 * math.sqrt(a) * alpha
        if kind == "Lowshelf":
            return (a * ((a + 1) - (a - 1) * cw + sa), 2 * a * ((a - 1) - (a + 1) * cw), a * ((a + 1) - (a - 1) * cw - sa),
                    (a + 1) + (a - 1) * cw + sa, -2 * ((a - 1) + (a + 1) * cw), (a + 1) + (a - 1) * cw - sa)
        return (a * ((a + 1) + (a - 1) * cw + sa), -2 * a * ((a - 1) + (a + 1) * cw), a * ((a + 1) + (a - 1) * cw - sa),
                (a + 1) - (a - 1) * cw + sa, 2 * ((a - 1) - (a + 1) * cw), (a + 1) - (a - 1) * cw - sa)
    return None  # pass filters and others never boost


def max_boost_db(filters, fs):
    """Highest point of the summed magnitude response (20 Hz - 20 kHz) of the given biquads, in dB."""
    coefs = [c for c in (_biquad_coefs((f.get("parameters") or {}).get("type"), f["parameters"], fs)
                         for f in filters if f.get("type") == "Biquad" and (f.get("parameters") or {}).get("freq"))
             if c is not None]
    peak = 0.0
    for i in range(240):
        freq = 20 * 1000 ** (i / 239)
        if freq >= fs / 2:
            break
        w = 2 * math.pi * freq / fs
        total = 0.0
        for b0, b1, b2, a0, a1, a2 in coefs:
            nr, ni = b0 + b1 * math.cos(w) + b2 * math.cos(2 * w), -(b1 * math.sin(w) + b2 * math.sin(2 * w))
            dr, di = a0 + a1 * math.cos(w) + a2 * math.cos(2 * w), -(a1 * math.sin(w) + a2 * math.sin(2 * w))
            total += 10 * math.log10((nr * nr + ni * ni) / (dr * dr + di * di))
        peak = max(peak, total)
    return peak


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
        self.mode = "room"          # room | flat | night | vocal
        self.bypass = False         # True in flat mode
        self.lowcut = False         # "Sub off" button: 80 Hz high-pass on its own
        self.dirty = False
        self.history = []
        self._last_undo_key = None
        self._last_undo_time = 0
        self._apply_task = None
        self.status = {}
        self.signal_levels_cmd = True
        self.error = None
        self.screen_on = True
        self.screen_owner = None    # the screen (websocket) that put the display to sleep
        self.reconnecting = False
        self.recover_delay = 5      # seconds until the next auto-restart attempt; backs off to 30
        self.recover_at = 0

    # ---------- settings ----------
    def _load_settings(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        s = copy.deepcopy(DEFAULT_SETTINGS)
        try:
            s.update(json.loads(SETTINGS_FILE.read_text()))
        except (OSError, ValueError):
            pass
        return s

    def save_settings(self):
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, indent=2))
        tmp.replace(SETTINGS_FILE)

    def save_settings_soon(self, delay=2.0):
        if getattr(self, "_settings_task", None) and not self._settings_task.done():
            self._settings_task.cancel()

        async def later():
            try:
                await asyncio.sleep(delay)
                self.save_settings()
            except asyncio.CancelledError:
                pass
        self._settings_task = asyncio.ensure_future(later())

    # ---------- listening modes ----------
    @staticmethod
    def is_tone(name, f):
        return (f.get("type") == "Biquad" and not name.startswith("__") and not re.match(r"(?i)room\b", name)
                and isinstance((f.get("parameters") or {}).get("gain"), (int, float)))

    def mode_tone(self):
        """Tone fader gains of the current mode, or None in Room EQ / Flat (the preset's own values apply)."""
        if self.mode not in DEFAULT_MODE_TONES:
            return None
        return self.settings.setdefault("mode_tones", {}).setdefault(self.mode, {})

    def view_base(self):
        """The preset as the current mode sees it: tone fader gains replaced by the mode's values."""
        cfg = copy.deepcopy(self.base)
        tones = self.mode_tone()
        if cfg is not None and tones is not None:
            for name, f in (cfg.get("filters") or {}).items():
                if self.is_tone(name, f):
                    f["parameters"]["gain"] = float(tones.get(name, 0.0))
        return cfg

    # ---------- touchscreen backlight ----------
    def apply_backlight(self):
        """Backlight off while asleep, otherwise at the saved brightness."""
        if BACKLIGHT_DIR is None:
            return
        d = Path(BACKLIGHT_DIR)
        try:
            top = int((d / "max_brightness").read_text())
            pct = max(10, min(100, int(self.settings.get("brightness", 100))))
            (d / "brightness").write_text(str(round(top * pct / 100) if self.screen_on else 0))
        except (OSError, ValueError) as exc:
            self.error = f"Backlight: {exc}"

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
        """Config actually sent to CamillaDSP: base plus mode, low cut and switched-off filters."""
        cfg = self.view_base()
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
        if self.mode == "night" and not self.bypass:
            cfg["processors"] = dict(cfg.get("processors") or {}, __night_comp=copy.deepcopy(NIGHT_COMPRESSOR))
            steps.append({"type": "Processor", "name": "__night_comp"})
        cfg["pipeline"] = steps
        if self.settings.get("auto_preamp") and not self.bypass:
            gain = self.auto_preamp_db(cfg)
            for f in (cfg.get("filters") or {}).values():
                if f.get("type") == "Gain":
                    f.setdefault("parameters", {})["gain"] = gain
        return cfg

    def auto_preamp_db(self, cfg=None):
        """Preamp gain that cancels the largest boost of the filters currently in the pipeline."""
        cfg = cfg or self.effective()
        names = {n for st in cfg.get("pipeline") or [] if st.get("type") == "Filter" for n in st.get("names", [])}
        flts = [f for n, f in (cfg.get("filters") or {}).items() if n in names]
        try:
            fs = int(cfg.get("devices", {}).get("samplerate", 48000))
        except (TypeError, ValueError):
            fs = 48000
        return -round(max_boost_db(flts, fs) + 0.1, 1) if flts else 0.0

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
        self.history.append((copy.deepcopy(self.base), sorted(self.disabled()),
                             copy.deepcopy(self.settings.get("mode_tones", {}))))
        del self.history[:-60]

    # ---------- model sent to the screens ----------
    def model(self):
        filters, seen = [], set()
        base = self.view_base() or {}
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
            "mode": self.mode,
            "bypass": self.bypass,
            "lowcut": self.lowcut,
            "compressor": self.mode == "night" and not self.bypass,
            "lowcut_freq": self.settings["lowcut_freq"],
            "dirty": self.dirty,
            "can_undo": bool(self.history),
            "settings": {k: self.settings[k] for k in
                         ("background", "background_file", "logo_file", "opacity",
                          "brightness", "sleep_minutes", "auto_preamp")},
            "sleep_choices": SLEEP_CHOICES,
            "has_backlight": BACKLIGHT_DIR is not None,
            "screen_on": self.screen_on,
            "auto_preamp": bool(self.settings.get("auto_preamp")),
            "auto_preamp_db": self.auto_preamp_db() if self.base and self.settings.get("auto_preamp") else None,
            "reconnecting": self.reconnecting,
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
    async def handle(self, msg, ws=None):
        cmd = msg.get("cmd")
        if cmd == "screen":
            # Sent by the touchscreen page: on=False after its idle time, on=True on touch.
            self.screen_on = bool(msg.get("on"))
            self.screen_owner = None if self.screen_on else ws
            self.apply_backlight()
            return
        if cmd == "reconnect":
            if not self.reconnecting:
                asyncio.ensure_future(self.reconnect())
            return
        if cmd == "brightness":
            # Live while dragging; saved to settings.json only when save is true (the slider is released).
            self.settings["brightness"] = max(10, min(100, int(msg["value"])))
            self.apply_backlight()
            if msg.get("save"):
                self.save_settings()
                await self.broadcast_state()
            return
        if self.base is None and cmd not in ("settings", "preset"):
            await self.load_active()
        if cmd == "set_param":
            name, param, value = msg["name"], msg["param"], msg["value"]
            f = self.base["filters"].get(name)
            if f is None:
                return
            self.push_undo((name, param))
            tones = self.mode_tone()
            if tones is not None and param == "gain" and self.is_tone(name, f):
                tones[name] = round(float(value), 3)
                self.save_settings_soon()
            else:
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
            if msg.get("mode") in MODES:
                self.mode = msg["mode"]
                self.bypass = self.mode == "flat"
                await self.apply()
        elif cmd == "set_bypass":
            self.bypass = bool(msg["value"])
            if self.bypass:
                self.mode = "flat"
            elif self.mode == "flat":
                self.mode = "room"
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
                self.base, off, tones = self.history.pop()
                self.settings["mode_tones"] = tones
                self.set_disabled(off)
                self._last_undo_key = None
                self.dirty = True
                await self.apply()
        elif cmd == "settings":
            for k in ("background", "opacity", "logo_file", "background_file"):
                if k in msg.get("values", {}):
                    self.settings[k] = msg["values"][k]
            if int(msg.get("values", {}).get("sleep_minutes", -1)) in SLEEP_CHOICES:
                self.settings["sleep_minutes"] = int(msg["values"]["sleep_minutes"])
            if "auto_preamp" in msg.get("values", {}):
                self.settings["auto_preamp"] = bool(msg["values"]["auto_preamp"])
                self.save_settings()
                await self.apply()
                return
            self.save_settings()
            await self.broadcast_state()

    async def reconnect(self):
        """Run the reconnect helper, wait for CamillaDSP, then re-apply bypass / low cut / switched-off filters."""
        self.reconnecting = True
        await self.broadcast_state()
        try:
            proc = await asyncio.create_subprocess_exec(
                *RECONNECT_CMD, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError("timed out")
            if proc.returncode:
                lines = out.decode(errors="replace").strip().splitlines()
                raise RuntimeError(lines[-1] if lines else f"exit code {proc.returncode}")
            for _ in range(20):
                try:
                    await self.cdsp.call("GetState")
                    break
                except RuntimeError:
                    await asyncio.sleep(0.5)
            self.reconnecting = False
            await self.apply()
            notice = {"type": "notice", "text": "Reconnected", "ok": True}
        except (OSError, RuntimeError) as exc:
            notice = {"type": "notice", "text": f"Reconnect failed: {exc}", "ok": False}
        finally:
            self.reconnecting = False
        await self.broadcast(notice)
        await self.broadcast_state()

    async def auto_recover(self, state):
        """Restart processing after a device dropout, e.g. the KEF leaving USB when the TV turns on.

        CamillaDSP stops on a capture or playback error and stays Inactive even after the
        device returns. The KEF's power saving switches it off (and off USB) regularly, so
        nothing is tried while a device is missing; once both are present again the
        effective config is re-applied, keeping bypass, low cut and switched-off filters.
        Failed attempts back off from 5 to 30 seconds.
        """
        if state == "Running":
            self.recover_delay = 5
            return
        if state != "Inactive" or self.reconnecting or self.base is None:
            return
        now = time.monotonic()
        if now < self.recover_at:
            return
        try:
            reason = await self.cdsp.call("GetStopReason")
        except RuntimeError:
            return
        if not isinstance(reason, dict):   # "None" or "Done": stopped on purpose, leave it
            return
        if not self.devices_present():
            return
        self.recover_at = now + self.recover_delay
        self.recover_delay = min(30, self.recover_delay * 2)
        await self.apply()
        await self.broadcast({"type": "notice", "ok": True,
                              "text": "Speakers back: audio restarted"})

    def devices_present(self):
        """True when the ALSA cards named in the config (hw:CARD=...) exist right now."""
        devs = (self.base or {}).get("devices") or {}
        for side in ("capture", "playback"):
            m = re.search(r"CARD=([^,]+)", str((devs.get(side) or {}).get("device", "")))
            if m and not Path(f"/proc/asound/{m.group(1)}").exists():
                return False
        return True

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
            await self.auto_recover(st["state"])
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
                    await app_state.handle(json.loads(msg.data), ws)
                except Exception as exc:  # report, keep the connection alive
                    app_state.error = f"{type(exc).__name__}: {exc}"
                    await app_state.broadcast_state()
    finally:
        app_state.clients.discard(ws)
        if ws is app_state.screen_owner and not app_state.screen_on:
            # The touchscreen page went away while dark (browser closed): never leave it stuck off.
            app_state.screen_on, app_state.screen_owner = True, None
            app_state.apply_backlight()
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
    app_state.apply_backlight()
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
