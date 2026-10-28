# Runs on the Pico (MicroPython). Read-only access to an AT45DB321E DataFlash.
# Driven by scripts/minidsp_flash.py over the USB serial port (raw REPL):
#   import at45; at45.serve()
# Commands, one per line: "probe", "id", "read <baud>", "quit".
# Wiring: GP2 SCK, GP3 MOSI (chip SI), GP4 MISO (chip SO), GP5 CS, GND to board ground.
import sys, time, hashlib, binascii
from machine import Pin, SPI

SCK, MOSI, MISO, CS = 2, 3, 4, 5
SLOW = 1_000_000
cs = Pin(CS, Pin.OUT, value=1)
spi = None


def spi_on(baud=SLOW):
    global spi
    spi = SPI(0, baudrate=baud, polarity=0, phase=0,
              sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))


def cmd(op, n):
    buf = bytearray(n)
    cs(0)
    spi.write(op)
    spi.readinto(buf)
    cs(1)
    return buf


def say(*parts):
    sys.stdout.write(" ".join(str(p) for p in parts) + "\n")


def probe():
    # MISO level with the Pico's pull-down and pull-up, CS high (chip SO is off).
    # Follows the pull = nothing drives it (no contact or idle line).
    # Same level both times = something on the board drives it or a strong resistor.
    levels = []
    for pull in (Pin.PULL_DOWN, Pin.PULL_UP):
        p = Pin(MISO, Pin.IN, pull)
        time.sleep_ms(5)
        levels.append(p.value())
    spi_on()
    say("PROBE", "miso_pulldown=%d" % levels[0], "miso_pullup=%d" % levels[1])


def ident():
    cmd(b"\xab", 0)            # resume from deep power-down (harmless otherwise)
    cs(0); time.sleep_us(50); cs(1)   # CS toggle ends ultra-deep power-down
    time.sleep_ms(1)
    jedec = cmd(b"\x9f", 5)
    st = cmd(b"\xd7", 2)
    say("ID", binascii.hexlify(jedec).decode(), "STATUS", binascii.hexlify(st).decode())


def size_from_status(st):
    # Status byte 1: bit0 = 1 -> 512-byte pages, 0 -> 528-byte pages (8192 pages).
    return 8192 * (512 if st & 1 else 528)


def read(baud):
    spi_on(baud)
    st = cmd(b"\xd7", 1)[0]
    total = size_from_status(st)
    say("DATA", total)
    h = hashlib.sha256()
    out = sys.stdout.buffer
    buf = bytearray(4096)
    mv = memoryview(buf)
    cs(0)
    spi.write(b"\x03\x00\x00\x00")   # continuous array read from address 0
    left = total
    while left:
        n = min(left, len(buf))
        spi.readinto(mv[:n])
        h.update(mv[:n])
        out.write(mv[:n])
        left -= n
    cs(1)
    spi_on()
    say("\nEND", binascii.hexlify(h.digest()).decode())


def serve():
    spi_on()
    say("READY")
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            continue
        parts = line.split()
        try:
            if parts[0] == "probe":
                probe()
            elif parts[0] == "id":
                ident()
            elif parts[0] == "read":
                read(int(parts[1]) if len(parts) > 1 else SLOW)
            elif parts[0] == "quit":
                say("BYE")
                return
            else:
                say("ERR unknown", parts[0])
        except Exception as e:
            cs(1)
            say("ERR", repr(e))
