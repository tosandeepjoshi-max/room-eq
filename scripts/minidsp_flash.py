"""Read the miniDSP's AT45DB321E flash with a Raspberry Pi Pico (read only).

The Pico runs MicroPython plus pico/at45.py. Wiring: GP2 SCK, GP3 MOSI -> chip SI,
GP4 MISO <- chip SO, GP5 CS, Pico GND -> board ground; the board uses its own supply.

  python scripts/minidsp_flash.py firmware      # copy MicroPython to a Pico in BOOTSEL mode
  python scripts/minidsp_flash.py install       # copy pico/at45.py to the Pico
  python scripts/minidsp_flash.py probe         # MISO line test (contact check)
  python scripts/minidsp_flash.py id            # JEDEC ID + status (expect 1f 27 01 ...)
  python scripts/minidsp_flash.py read out.bin [--baud 1000000]
  python scripts/minidsp_flash.py compare a.bin b.bin
"""
import argparse
import hashlib
import shutil
import string
import subprocess
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "pico" / "firmware"
PICO_SCRIPT = ROOT / "pico" / "at45.py"
PICO_VID = 0x2E8A


def find_port():
    ports = [p.device for p in list_ports.comports() if p.vid == PICO_VID]
    if not ports:
        sys.exit("No Pico serial port found. Is MicroPython on it and the USB cable plugged in?")
    return ports[0]


def find_bootsel_drive():
    for letter in string.ascii_uppercase:
        if Path(f"{letter}:/INFO_UF2.TXT").exists():
            return Path(f"{letter}:/")
    sys.exit("No RPI-RP2 drive found. Hold BOOTSEL while you plug the Pico in.")


class Pico:
    """Starts at45.serve() through the raw REPL and talks its line protocol."""

    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=5)
        self.s.write(b"\r\x03\x03")          # stop whatever runs
        time.sleep(0.2)
        self.s.reset_input_buffer()
        self.s.write(b"\x01")                # raw REPL
        self._wait(b"raw REPL; CTRL-B to exit\r\n>")
        self.s.write(b"import at45\nat45.serve()\n\x04")
        self._wait(b"OK")
        line = self.line()
        if line != "READY":
            sys.exit(f"Pico did not start at45.serve(): {line!r} (run 'install' first?)")

    def _wait(self, token):
        data = b""
        end = time.time() + 5
        while token not in data:
            if time.time() > end:
                sys.exit(f"Pico did not answer (got {data[-80:]!r})")
            data += self.s.read(max(1, self.s.in_waiting))

    def line(self):
        return self.s.readline().decode(errors="replace").strip()

    def send(self, text):
        self.s.write(text.encode() + b"\n")

    def close(self):
        self.send("quit")
        self.line()
        self.s.write(b"\x02")                # back to the normal REPL
        self.s.close()


def cmd_firmware(_):
    uf2 = sorted(FIRMWARE_DIR.glob("RPI_PICO-*.uf2"))
    if not uf2:
        sys.exit(f"No .uf2 in {FIRMWARE_DIR}")
    drive = find_bootsel_drive()
    print(f"Copying {uf2[-1].name} to {drive} ...")
    shutil.copy(uf2[-1], drive)
    print("Done. The Pico restarts with MicroPython.")


def cmd_install(_):
    mpremote = [sys.executable, "-m", "mpremote", "connect", find_port()]
    subprocess.run(mpremote + ["cp", str(PICO_SCRIPT), ":at45.py"], check=True)
    print("at45.py is on the Pico.")


def cmd_probe(_):
    p = Pico(find_port())
    p.send("probe")
    line = p.line()
    p.close()
    print(line)
    if "pulldown=0" in line and "pullup=1" in line:
        print("MISO follows the Pico's pull: nothing on the board drives it with CS high (expected).")
    elif "pulldown=1" in line:
        print("MISO is held high by the board (pull-up resistor or the XMOS).")
    else:
        print("MISO is held low by the board.")


def cmd_id(_):
    p = Pico(find_port())
    p.send("id")
    line = p.line()
    p.close()
    print(line)
    jedec = line.split()[1] if line.startswith("ID") else ""
    if jedec.startswith("1f27"):
        print("AT45DB321 answers. Contact is good.")
    elif jedec in ("ffffffffff", "0000000000"):
        print("No answer from the chip (all ff / 00). Check contact, CS and the chip's power.")
    else:
        print("Unexpected ID: check the wiring, or the XMOS is driving the bus.")


def cmd_read(args):
    out = Path(args.out)
    p = Pico(find_port())
    p.send(f"read {args.baud}")
    head = p.line()
    if not head.startswith("DATA"):
        sys.exit(f"Read failed: {head}")
    total = int(head.split()[1])
    print(f"Reading {total} bytes at {args.baud} Hz ...")
    h = hashlib.sha256()
    got = 0
    start = time.time()
    p.s.timeout = 10
    with open(out, "wb") as f:
        while got < total:
            chunk = p.s.read(min(65536, total - got))
            if not chunk:
                sys.exit(f"Timed out after {got} bytes")
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            print(f"\r{got * 100 // total:3d} %", end="", flush=True)
    p.s.timeout = 5
    tail = ""
    while not tail.startswith("END"):
        tail = p.line()
    p.close()
    ok = tail.split()[1] == h.hexdigest()
    print(f"\n{out}: {got} bytes in {time.time() - start:.0f} s, sha256 {h.hexdigest()[:16]}...")
    print("Transfer check OK." if ok else "Transfer check FAILED: the file differs from what the Pico read.")
    blank = Path(out).read_bytes()
    if blank.count(0xFF) == len(blank):
        print("Warning: every byte is 0xFF (no data from the chip).")
    if not ok:
        sys.exit(1)


def cmd_compare(args):
    a, b = Path(args.a).read_bytes(), Path(args.b).read_bytes()
    if len(a) != len(b):
        sys.exit(f"Sizes differ: {len(a)} vs {len(b)}")
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if not diff:
        print(f"Identical ({len(a)} bytes). The backup is good.")
    else:
        print(f"{len(diff)} bytes differ, first at 0x{diff[0]:06x}. Read again; contact is not stable.")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("firmware")
    sub.add_parser("install")
    sub.add_parser("probe")
    sub.add_parser("id")
    r = sub.add_parser("read")
    r.add_argument("out")
    r.add_argument("--baud", type=int, default=1_000_000)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args()
    {"firmware": cmd_firmware, "install": cmd_install, "probe": cmd_probe, "id": cmd_id,
     "read": cmd_read, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
