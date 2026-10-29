"""Read an Atmel/Adesto AT45DB321E DataFlash with a Raspberry Pi Pico running MicroPython.

Usage (PC side, Pico on USB with MicroPython):
  python scripts/at45_pico.py ports                  list serial ports
  python scripts/at45_pico.py id   [--port COM5]     JEDEC ID and status (page size, ready)
  python scripts/at45_pico.py read out.bin [--port COM5] [--baud 4000000]
  python scripts/at45_pico.py compare a.bin b.bin

Wiring (the AT45 pinout is NOT the usual 25-series one):
  Pico GP2 (SPI0 SCK) -> chip pin 2 SCK      Pico GP3 (SPI0 TX)  -> chip pin 1 SI
  Pico GP4 (SPI0 RX)  -> chip pin 8 SO       Pico GP5            -> chip pin 4 CS
  Pico 3V3 OUT (pin 36) -> chip pin 6 VCC, pin 3 RESET, pin 5 WP   Pico GND -> chip pin 7 GND

The script sends a small program to the Pico's raw REPL. "read" does one Continuous Array Read
(0x0B) over the whole array, which wraps through every page in either page-size mode, and streams
it back as hex blocks with a CRC each, so a transfer error is caught rather than saved.
Nothing here writes to the chip.
"""
import argparse
import binascii
import sys
import time

import serial
from serial.tools import list_ports

PICO_CODE = r'''
import machine, binascii, sys
cs = machine.Pin(5, machine.Pin.OUT, value=1)
spi = machine.SPI(0, baudrate=%(baud)d, polarity=0, phase=0, bits=8,
                  sck=machine.Pin(2), mosi=machine.Pin(3), miso=machine.Pin(4))
def xfer(cmd, n):
    cs(0); spi.write(bytes(cmd)); r = spi.read(n); cs(1); return r
idb = xfer([0x9F], 5)
st = xfer([0xD7], 2)
print("ID", binascii.hexlify(idb).decode(), "ST", binascii.hexlify(st).decode())
if %(read)d:
    page = 512 if st[0] & 1 else 528
    total = 8192 * page
    print("SIZE", total, page)
    blk = 2048
    buf = bytearray(blk)
    cs(0)
    spi.write(b"\x0b\x00\x00\x00\x00")       # continuous array read from 0, one dummy byte
    i = 0
    while i * blk < total:
        n = min(blk, total - i * blk)
        mv = memoryview(buf)[:n]
        spi.readinto(mv)
        print("B", i, binascii.hexlify(mv).decode(), binascii.crc32(mv))
        i += 1
    cs(1)
    print("END", i)
'''


def find_port(port):
    if port:
        return port
    for p in list_ports.comports():
        if p.vid == 0x2E8A:          # Raspberry Pi (MicroPython on RP2040)
            return p.device
    sys.exit("No Pico found. Plug it in (MicroPython running) or pass --port COMx.")


def run(port, code):
    """Run code in the Pico's raw REPL; yield output lines as they arrive."""
    s = serial.Serial(port, 115200, timeout=5)
    s.write(b"\r\x03\x03")
    time.sleep(0.2)
    s.reset_input_buffer()
    s.write(b"\x01")
    if b"raw REPL" not in s.read_until(b">"):
        sys.exit("No MicroPython raw REPL on " + port)
    s.write(code.encode() + b"\x04")
    if s.read(2) != b"OK":
        sys.exit("Pico did not accept the program")
    buf = b""
    while True:
        chunk = s.read(s.in_waiting or 1)
        if not chunk:
            raise TimeoutError("no data from the Pico for 5 s")
        buf += chunk
        if b"\x04" in buf:
            out, rest = buf.split(b"\x04", 1)
            for line in out.decode(errors="replace").splitlines():
                yield line
            err = rest + s.read_until(b"\x04")
            err = err.rstrip(b"\x04>").strip()
            s.write(b"\x02")
            s.close()
            if err:
                sys.exit("Pico error:\n" + err.decode(errors="replace"))
            return
        *lines, buf = buf.split(b"\n")
        for line in lines:
            yield line.decode(errors="replace").rstrip("\r")


def describe(idhex, sthex):
    idb, st = bytes.fromhex(idhex), bytes.fromhex(sthex)
    print(f"JEDEC ID: {idhex}  (expected 1f2701... for AT45DB321E)")
    print(f"status:   {st[0]:08b}  ready={bool(st[0] & 0x80)}  density bits={(st[0] >> 2) & 0xF:04b} "
          f"(1101 = 32 Mbit)  protect={bool(st[0] & 2)}  page={'512' if st[0] & 1 else '528'} bytes")
    if idb[:2] != b"\x1f\x27":
        print("WARNING: not the expected ID. Check wiring, VCC/RESET/WP at 3.3 V, and that the chip "
              "is powered. All 0xff or 0x00 = no answer.")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ports", "id", "read", "compare"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=4_000_000, help="SPI clock, Hz")
    a = ap.parse_args()

    if a.cmd == "ports":
        for p in list_ports.comports():
            print(p.device, p.description, f"VID={p.vid:04X}" if p.vid else "")
        return
    if a.cmd == "compare":
        x, y = (open(f, "rb").read() for f in a.files[:2])
        diff = [i for i in range(min(len(x), len(y))) if x[i] != y[i]]
        print(f"sizes {len(x)} / {len(y)}; differing bytes: {len(diff)}"
              + (f" (first at 0x{diff[0]:06x})" if diff else ""))
        print("IDENTICAL" if not diff and len(x) == len(y) else "DIFFERENT")
        return

    port = find_port(a.port)
    code = PICO_CODE % {"baud": a.baud, "read": int(a.cmd == "read")}
    out, total, expect, t0 = None, 0, 0, time.time()
    for line in run(port, code):
        p = line.split()
        if not p:
            continue
        if p[0] == "ID":
            ok = describe(p[1], p[3])
            if a.cmd == "read" and not ok:
                sys.exit("Not reading: the chip did not answer correctly.")
        elif p[0] == "SIZE":
            expect = int(p[1])
            print(f"reading {expect} bytes ({p[2]}-byte pages) at {a.baud / 1e6:.1f} MHz ...")
            out = open(a.files[0], "wb")
        elif p[0] == "B":
            data = binascii.unhexlify(p[2])
            if binascii.crc32(data) != int(p[3]):
                sys.exit(f"CRC error in block {p[1]}: transfer problem, read again")
            out.write(data)
            total += len(data)
            if int(p[1]) % 128 == 0:
                print(f"  {total * 100 // expect:3d} %", end="\r", flush=True)
        elif p[0] == "END":
            out.close()
            print(f"done: {total} bytes in {time.time() - t0:.0f} s -> {a.files[0]}")
            if total != expect:
                sys.exit("size mismatch")
            data = open(a.files[0], "rb").read()
            if data.count(0xFF) == len(data) or data.count(0) == len(data):
                print("WARNING: the whole image is 0xff or 0x00: probably no real read.")
        else:
            print(line)


if __name__ == "__main__":
    main()
