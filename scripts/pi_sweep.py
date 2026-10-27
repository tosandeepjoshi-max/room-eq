"""Measure the room from the Pi itself: play the Pocket sweep through CamillaDSP, record the UMIK-1.

Runs ON THE PI (needs numpy and aiohttp), with the UMIK-1 plugged into a Pi USB port:
  scp scripts/pi_sweep.py joshis-pi:/tmp/ && ssh joshis-pi python3 /tmp/pi_sweep.py flat room
Then copy /tmp/pi_sweep/*.wav to the PC and analyse them with scripts/pocket_analyse.py.
With --play-only the Pi only plays (UMIK-1 on the PC, recorded there, e.g. with ffmpeg).
--level=-20 sets the sweep level in dBFS (default -20; the Pocket page uses -6, too loud at home).
Set the sub to "On" (not Auto) first: in auto standby it wakes too late for the low end of the sweep.

For each mode given (flat, room, vocal, night) it switches the Room EQ UI to that mode, takes the
effective config CamillaDSP runs, swaps the capture device (the Shield gadget) for a WAV file of
the sweep, and records the UMIK-1 meanwhile, so the sweep passes the real filters, the real KEF
and the sub. Afterwards it switches the UI back to the mode it found, which restores the normal
capture device. The sweep is the Pocket page's (18 Hz-20 kHz, 8 s), at -20 dBFS by default.
"""
import asyncio
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from aiohttp import ClientSession

UI_WS = "http://localhost:8080/ws"
CAMILLA_WS = "ws://127.0.0.1:1234"
OUT = Path("/tmp/pi_sweep")
FS = 192000                       # CamillaDSP runs at 192 kHz; the file must match
REC_FS = 48000                    # UMIK-1 rate
SWEEP = dict(f1=18.0, f2=20000.0, T=8.0, amp=0.1)   # as scripts/pocket_analyse.py, but -20 dBFS
# Swapping the capture device restarts the stream to the KEF, and after that the start of a sweep is
# lost: the chain (most likely the KEF) stays muted until the signal is strong enough, and the deep
# start of a sweep is not. Silence, a quiet tone or a longer lead-in did not help (2026-10-27). So the
# file plays the sweep twice: the first wakes everything, the second is measured. pocket_analyse
# picks the loudest 8 s, which is the complete second sweep (pause any other playback first).
LEAD, GAP, POST = 0.5, 3.0, 2.0   # seconds
BED_DB = -50.0                    # quiet noise instead of digital silence between the parts


def make_sweep(fs):
    f1, f2, T, amp = SWEEP["f1"], SWEEP["f2"], SWEEP["T"], SWEEP["amp"]
    n = round(T * fs)
    t = np.arange(n) / fs
    L = np.log(f2 / f1)
    s = np.sin(2 * np.pi * f1 * T / L * (np.exp(t * L / T) - 1))
    fi, fo = round(0.05 * fs), round(0.01 * fs)
    s[:fi] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(fi) / fi)
    s[n - fo + 1:] *= 0.5 - 0.5 * np.cos(np.pi * (n - np.arange(n - fo + 1, n)) / fo)
    return s * amp


def write_sweep(path):
    rng = np.random.default_rng(1)
    bed = lambda sec: 10 ** (BED_DB / 20) * rng.standard_normal(round(sec * FS)) / 3
    sweep = make_sweep(FS)
    sig = np.concatenate([bed(LEAD), sweep, bed(GAP), sweep, bed(POST)])
    pcm = np.round(np.clip(sig, -1, 1) * (2 ** 31 - 1)).astype("<i4")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(4)
        w.setframerate(FS)
        w.writeframes(np.repeat(pcm, 2).tobytes())
    return len(sig) / FS


def umik_card():
    out = subprocess.run(["arecord", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        m = re.match(r"card \d+: (\S+) \[([^\]]*)\]", line)
        if m and re.search(r"umik|u18db|minidsp", line, re.I):
            return m.group(1)
    sys.exit("UMIK-1 not found (arecord -l). Plug it into a Pi USB port.")


async def camilla(ws, cmd, arg=None):
    await ws.send_str(json.dumps(cmd if arg is None else {cmd: arg}))
    while True:
        reply = json.loads((await ws.receive()).data)
        if cmd in reply:
            body = reply[cmd]
            if body.get("result") != "Ok":
                raise RuntimeError(f"{cmd}: {body}")
            return body.get("value")


async def ui_mode(ui, mode=None):
    """Switch the UI to mode (if given) and return the mode it reports."""
    if mode:
        await ui.send_str(json.dumps({"cmd": "set_mode", "mode": mode}))
    while True:
        msg = json.loads((await asyncio.wait_for(ui.receive(), 10)).data)
        if msg.get("type") == "state" and (mode is None or msg.get("mode") == mode):
            return msg["mode"]


async def main(modes, play_only=False):
    OUT.mkdir(exist_ok=True)
    card = None if play_only else umik_card()
    sweep_file = OUT / "sweep_192k.wav"
    length = write_sweep(sweep_file)
    if not Path("/proc/asound/Speaker").exists():
        sys.exit("KEF (ALSA card Speaker) not present: wake the speakers first.")
    async with ClientSession() as s:
        async with s.ws_connect(UI_WS) as ui, s.ws_connect(CAMILLA_WS, max_msg_size=0) as cd:
            start_mode = await ui_mode(ui)
            print(f"UMIK-1 = {card or 'on the PC'}; UI mode now {start_mode}")
            try:
                for mode in modes:
                    await ui_mode(ui, mode)
                    await asyncio.sleep(1.5)
                    cfg = json.loads(await camilla(cd, "GetConfigJson"))
                    dev = cfg["devices"]
                    dev["capture"] = {"type": "WavFile", "filename": str(sweep_file)}
                    dev["enable_rate_adjust"] = False
                    rec = OUT / f"{mode}.wav"
                    arec = None if play_only else subprocess.Popen(
                        ["arecord", "-q", "-D", f"plughw:CARD={card},DEV=0", "-f", "S24_3LE", "-c", "1",
                         "-r", str(REC_FS), "-d", str(int(length + 3)), str(rec)])
                    await asyncio.sleep(0.5)
                    await camilla(cd, "SetConfigJson", json.dumps(cfg))
                    print(f"{mode}: playing the sweep ({length:.0f} s)" + ("" if play_only else f", recording {rec}"))
                    if arec:
                        arec.wait()
                    else:
                        await asyncio.sleep(length + 0.5)
                    await asyncio.sleep(1)
            finally:
                # set_mode always re-applies the effective config, so this also restores the Shield input.
                await ui.send_str(json.dumps({"cmd": "set_mode", "mode": start_mode}))
                await asyncio.sleep(2)
                print(f"UI back in {start_mode}; normal input restored")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--level="):
            SWEEP["amp"] = 10 ** (float(a.split("=", 1)[1]) / 20)
    asyncio.run(main(args or ["flat", "room"], play_only="--play-only" in sys.argv))
