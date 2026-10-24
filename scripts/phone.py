"""Move files between this PC and the user's Android phone over wireless adb.

Usage:
  python scripts/phone.py status
  python scripts/phone.py push <file> [...] [--to Download/car_eq_wavelet]
  python scripts/phone.py pull-recordings <YYYY_MM_DD> [--out measurements/<date>_car]

The phone must have Wireless debugging on and be paired once (adb pair <ip:port> <code>);
after that adb finds it on the same Wi-Fi by itself (mDNS). Recordings come from
USB Audio Recorder PRO: /sdcard/Documents/USBAudioRecorderPRO/Recordings/Record_<date>_*.wav
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REC_DIR = "/sdcard/Documents/USBAudioRecorderPRO/Recordings"
PHONE_GUID = "adb-10AG5L1NLF002QS"          # vivo V2562; the Shield also shows up in adb, never use it


def adb_path():
    found = shutil.which("adb")
    if found:
        return found
    p = Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Packages"
    hits = list(p.glob("Google.PlatformTools_*/platform-tools/adb.exe"))
    if not hits:
        sys.exit("adb not found: winget install Google.PlatformTools")
    return str(hits[0])


ADB = adb_path()


def run(*args, check=True):
    r = subprocess.run([ADB, *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def phone_serial():
    for line in run("devices").splitlines()[1:]:
        parts = line.split()
        if parts and parts[0].startswith(PHONE_GUID) and parts[1] == "device":
            return parts[0]
    # not connected yet: adb usually connects over mDNS within a few seconds
    for line in run("mdns", "services", check=False).splitlines():
        parts = line.split()
        if parts and parts[0].startswith(PHONE_GUID) and "_adb-tls-connect" in line:
            run("connect", parts[-1], check=False)
            return phone_serial_once()
    sys.exit("phone not found: turn on Wireless debugging (same Wi-Fi), or pair again with adb pair")


def phone_serial_once():
    for line in run("devices").splitlines()[1:]:
        parts = line.split()
        if len(parts) > 1 and PHONE_GUID in parts[0] and parts[1] == "device":
            return parts[0]
    sys.exit("phone did not connect")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("push")
    p.add_argument("files", nargs="+")
    p.add_argument("--to", default="Download")
    q = sub.add_parser("pull-recordings")
    q.add_argument("date", help="YYYY_MM_DD as in the file names")
    q.add_argument("--out")
    a = ap.parse_args()

    s = phone_serial()
    if a.cmd == "status":
        print("phone connected:", s)
        print(run("-s", s, "shell", f"ls {REC_DIR} | tail -5"))
    elif a.cmd == "push":
        dest = "/sdcard/" + a.to.strip("/")
        run("-s", s, "shell", "mkdir", "-p", dest)
        for f in a.files:
            run("-s", s, "push", f, dest + "/")
            print(f"pushed {f} -> {dest}/")
    else:
        names = [n for n in run("-s", s, "shell", f"ls {REC_DIR}").split() if n.startswith(f"Record_{a.date}")]
        if not names:
            sys.exit(f"no recordings for {a.date} in {REC_DIR}")
        out = Path(a.out or f"measurements/{a.date.replace('_', '-')}_car")
        out.mkdir(parents=True, exist_ok=True)
        for n in names:
            run("-s", s, "pull", f"{REC_DIR}/{n}", str(out / n))
            print(f"pulled {n}")
        print(f"{len(names)} recordings in {out}")


if __name__ == "__main__":
    main()
