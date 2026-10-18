#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial>=3.5"]
# ///
"""
me7_kline_probe.py - minimal K-line probes for an ME7 on a bench.

Three probes, each sending as little as possible:

  wake ADDR     5-baud slow init to ADDR (default 0x11), print the sync byte
                and key bytes, complete the handshake, then stop. No service
                requests are sent; the ECU drops the session on its own.
                55 EF 8F = KWP2000, 55 01 8A = KW1281. On the reference ECU,
                0x01 answers KW1281 and 0x11 answers KWP2000.

  boot          Send ONE 0x00 and read the C167 bootstrap loader's ID byte
                (0xC5 = C167 derivative, 0xD5 = parts with ID registers,
                0xAA = a loader core is already running).

  boot-listen   Open the port FIRST and print every byte that arrives while
                you power the ECU into bootmode, then send one 0x00 when you
                press Enter. Use this when bootmode seems dead: the loader
                auto-bauds on the first low pulse after reset and answers
                only once, so a power-up glitch on the K-line can use up its
                reply before any tool asks for it (see docs/bench-harness.md).

Useful sequence when a bootmode tool reports no response: do a clean entry,
run `wake 0x11`. Silence (when a normal power-up answers) means the CPU is in
the loader, so entry works and the problem is the link; then do a fresh entry
and run `boot-listen`.

Any probe sent to a waiting loader is taken as loader data, so do a fresh
bootmode entry before each `boot`/`boot-listen`, and after a `wake`.

Usage:
    me7_kline_probe.py COM8 wake [0x11]
    me7_kline_probe.py COM8 boot [--baud 57600]
    me7_kline_probe.py COM8 boot-listen [--baud 57600]
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("me7_kline_probe.py needs Python 3.12 or newer")

import argparse
import threading
import time

try:
    import serial
except ImportError:
    sys.exit("needs pyserial: pip install pyserial")

LOADER_IDS = {0x55: "8xC166", 0xA5: "early C167", 0xB5: "early C165",
              0xC5: "C167 derivative", 0xD5: "C167 family with ID registers",
              0xAA: "loader core already running"}


def read_n(s: serial.Serial, n: int, timeout: float) -> bytes:
    buf = bytearray()
    end = time.perf_counter() + timeout
    while len(buf) < n and time.perf_counter() < end:
        buf += s.read(n - len(buf))
    return bytes(buf)


def wake(port: str, addr: int) -> int:
    with serial.Serial(port, 10400, timeout=0.05) as s:
        s.break_condition = False
        time.sleep(0.4)                       # idle high >= W5
        s.reset_input_buffer()
        t = time.perf_counter()
        for bit in [0] + [(addr >> i) & 1 for i in range(8)] + [1]:
            s.break_condition = bit == 0      # K-line low = break
            t += 0.2
            while time.perf_counter() < t:
                pass
        s.break_condition = False
        s.reset_input_buffer()                # drop the echo of our own pattern
        sync = read_n(s, 3, 1.5)
        print(f"slow init 0x{addr:02X} @10400: {sync.hex(' ') or '(nothing)'}")
        if len(sync) != 3 or sync[0] != 0x55:
            print("-> no wake-up response")
            return 1
        kb1, kb2 = sync[1], sync[2]
        time.sleep(0.030)                     # W4
        s.write(bytes([kb2 ^ 0xFF]))
        tail = read_n(s, 2, 0.5)
        proto = "KW1281" if (kb1, kb2) == (0x01, 0x8A) else (
            "KWP2000" if kb2 == 0x8F else "unknown")
        print(f"  ~KB2 0x{kb2 ^ 0xFF:02X} sent, got back {tail.hex(' ') or '(nothing)'}")
        print(f"-> keywords 0x{kb1:02X} 0x{kb2:02X}: {proto}")
        return 0


def boot(port: str, baud: int) -> int:
    with serial.Serial(port, baud, timeout=0.05) as s:
        s.break_condition = False
        s.reset_input_buffer()
        s.write(b"\x00")
        got = read_n(s, 4, 2.0)
    return report_boot(got)


def report_boot(got: bytes) -> int:
    reply = got[1:] if got[:1] == b"\x00" else got     # first byte is our echo
    print(f"sent 00, received: {got.hex(' ') or '(nothing)'}")
    if not got:
        print("-> nothing at all, not even the echo: check the cable's K-line supply")
        return 1
    if not reply:
        print("-> no loader reply (only our echo)")
        return 1
    print(f"-> ID 0x{reply[0]:02X}: {LOADER_IDS.get(reply[0], 'unrecognised')}")
    return 0


def boot_listen(port: str, baud: int) -> int:
    s = serial.Serial(port, baud, timeout=0.02)
    s.break_condition = False
    seen: list[tuple[float, bytes]] = []
    stop = threading.Event()
    t0 = time.perf_counter()

    def reader() -> None:
        while not stop.is_set():
            b = s.read(64)
            if b:
                seen.append((time.perf_counter() - t0, bytes(b)))
                print(f"  [{time.perf_counter() - t0:6.2f}s] {b.hex(' ')}", flush=True)

    threading.Thread(target=reader, daemon=True).start()
    print(f"{port} open at {baud}, listening; nothing sent yet.")
    print("Power off, close the boot relay, power on, wait 2-3 s, open the boot relay.")
    input("Then press Enter to send one 0x00 ... ")
    mark = time.perf_counter() - t0
    s.write(b"\x00")
    time.sleep(2.0)
    stop.set()
    time.sleep(0.1)
    s.close()
    before = sum(len(b) for t, b in seen if t < mark)
    print(f"\nbytes seen BEFORE the probe: {before}"
          + ("  <- power-up glitches; feed the cable's pin 16 from constant 12 V" if before else ""))
    return report_boot(b"".join(b for t, b in seen if t >= mark))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial port of a dumb K-line cable, e.g. COM8")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wake", help="5-baud wake-up and key bytes")
    w.add_argument("addr", nargs="?", type=lambda v: int(v, 0), default=0x11)
    for name in ("boot", "boot-listen"):
        b = sub.add_parser(name)
        b.add_argument("--baud", type=int, default=57600)
    args = ap.parse_args()
    match args.cmd:
        case "wake":
            return wake(args.port, args.addr)
        case "boot":
            return boot(args.port, args.baud)
        case "boot-listen":
            return boot_listen(args.port, args.baud)
    return 2


if __name__ == "__main__":
    sys.exit(main())
