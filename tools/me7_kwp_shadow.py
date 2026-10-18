#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyserial>=3.5"]
# ///
"""
me7_kwp_shadow.py - read an ME7's 95040 EEPROM contents from its RAM shadow
over KWP2000 on the K-line, without opening the ECU.

READ-ONLY. The only services this tool can send are:
    1A ReadEcuIdentification   10 StartDiagnosticSession   23 ReadMemoryByAddress
    27 SecurityAccess (login)  3E TesterPresent            82 StopCommunication
send() refuses anything else, so it cannot write, erase or program.

What it reads: ME7 keeps the EEPROM in a RAM shadow, one 16-byte slot per
record id (page attribute table, see docs/95040-format.md). This tool reads
the slots and rebuilds a 512-byte page image. Pages that are not shadowed -
0 (signature), 18, 19, 28, 29 - are written as FF, so me7_95040.py treats
them as absent. It is therefore NOT a full chip dump and must not be written
back to an ECU. Use bootmode for a real dump.

Protocol follows NefMoto Open Source (Communication/KWP2000*.cs): slow init
at 0x11 (an ME7 that answers KW1281 at 0x01 offers KWP2000 here), one-byte
headers, additive checksum, development session 0x86 for ReadMemoryByAddress.
On the reference ECU the security login is refused (7F 27 10) but the read
still works in the development session; the tool tries the login and carries on.

Addresses are for 4Z7907551S software 1037367582 (shadow 0x383DA8, 21 slots).
Check another build's page table with me7_flash_info.py --table first.

Usage:
    me7_kwp_shadow.py COM8 out.bin            # also writes out.bin.raw and out.bin.log
    me7_kwp_shadow.py COM8 out.bin --shadow 0x383DA8 --slots 21
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("me7_kwp_shadow.py needs Python 3.12 or newer")

import argparse
import time
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("needs pyserial: pip install pyserial")

INIT_ADDR = 0x11
BAUD = 10400
ALLOWED = frozenset({0x1A, 0x27, 0x10, 0x3E, 0x23, 0x82})
P3_MIN = 0.060          # tester wait after an ECU response
P4 = 0.005              # tester inter-byte gap
KEY_TABLE_3F = 0x5FBD5DBD

# Page -> shadow record id for 1037367582 (page attribute table at 0x816E00).
PAGE_RECORD = (None, 0, 1, 2, 3, 4, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10,
               11, 11, 11, 12, 13, 14, 15, 16, 17, 18, 19, 19, 19, 20, 20)
# Pages sharing a record whose slot tracks only the record's first page.
NOT_TRACKED = frozenset({18, 19, 28, 29})


class Link:
    def __init__(self, port: str) -> None:
        self.s = serial.Serial(port, BAUD, timeout=0.02)
        self.log: list[str] = []

    def note(self, msg: str) -> None:
        print(msg)
        self.log.append(msg)

    def read_n(self, n: int, timeout: float) -> bytes:
        buf = bytearray()
        end = time.perf_counter() + timeout
        while len(buf) < n and time.perf_counter() < end:
            buf += self.s.read(n - len(buf))
        return bytes(buf)

    def wake(self) -> None:
        """ISO 9141/14230 5-baud slow init, then complete the key-byte handshake."""
        s = self.s
        s.break_condition = False
        time.sleep(0.4)
        s.reset_input_buffer()
        t = time.perf_counter()
        for bit in [0] + [(INIT_ADDR >> i) & 1 for i in range(8)] + [1]:
            s.break_condition = bit == 0
            t += 0.2
            while time.perf_counter() < t:
                pass
        s.break_condition = False
        s.reset_input_buffer()
        sync = self.read_n(3, 1.5)
        self.note(f"slow init 0x{INIT_ADDR:02X}: <- {sync.hex(' ') or 'nothing'}")
        if len(sync) != 3 or sync[0] != 0x55:
            raise ConnectionError("no KWP2000 wake-up response")
        time.sleep(0.030)
        s.write(bytes([sync[2] ^ 0xFF]))
        tail = self.read_n(2, 0.5)
        self.note(f"  ~KB2 sent; <- {tail.hex(' ') or 'nothing'}")
        if len(tail) != 2 or tail[1] != INIT_ADDR ^ 0xFF:
            raise ConnectionError("key-byte handshake did not complete")

    def send(self, payload: bytes) -> None:
        if payload[0] not in ALLOWED:
            raise PermissionError(f"service 0x{payload[0]:02X} is not allowed (read-only tool)")
        msg = bytes([len(payload)]) + payload
        msg += bytes([sum(msg) & 0xFF])
        time.sleep(P3_MIN)
        for b in msg:
            self.s.write(bytes([b]))
            echo = self.read_n(1, 0.1)
            if echo != bytes([b]):
                raise IOError(f"K-line echo mismatch: sent {b:02X}, got {echo.hex() or 'nothing'}")
            time.sleep(P4)
        self.note(f"  -> {msg.hex(' ')}")

    def recv(self, timeout: float = 1.0) -> bytes:
        """Service bytes of one ECU response; waits through 7F xx 78 (pending)."""
        while True:
            fmt = self.read_n(1, timeout)
            if not fmt:
                raise TimeoutError("no response from ECU")
            hdr = bytearray(fmt)
            if fmt[0] & 0xC0:
                hdr += self.read_n(2, 0.1)
            n = fmt[0] & 0x3F
            if n == 0:
                lb = self.read_n(1, 0.1)
                hdr += lb
                n = lb[0] if lb else 0
            body = self.read_n(n + 1, 0.5)
            raw = bytes(hdr) + body
            self.note(f"  <- {raw.hex(' ')}")
            if len(body) != n + 1 or (sum(raw[:-1]) & 0xFF) != raw[-1]:
                raise IOError("bad length or checksum in ECU response")
            data = body[:-1]
            if len(data) >= 3 and data[0] == 0x7F and data[2] == 0x78:
                continue
            return data

    def request(self, payload: bytes, must_succeed: bool = True) -> bytes:
        self.send(payload)
        data = self.recv()
        if data[0] == 0x7F:
            self.note(f"     negative response to 0x{data[1]:02X}: code 0x{data[2]:02X}")
            if must_succeed:
                raise RuntimeError(f"ECU rejected 0x{payload[0]:02X} with 0x{data[2]:02X}")
        return data

    def close(self) -> None:
        self.s.close()


def key_from_seed(seed: bytes) -> bytes:
    k = int.from_bytes(seed, "big")
    for _ in range(5):
        k = ((((k << 1) & 0xFFFFFFFF) | 1) ^ KEY_TABLE_3F) if k & 0x80000000 else (k << 1) & 0xFFFFFFFF
    return k.to_bytes(4, "big")


def try_login(link: Link) -> None:
    d = link.request(bytes([0x27, 0x01]), must_succeed=False)
    if d[0] == 0x7F:
        link.note("     login refused; continuing (the read may still be served)")
        return
    seed = d[2:6]
    if len(seed) < 4 or not any(seed):
        link.note("     security already open")
        return
    d = link.request(bytes([0x27, 0x02]) + key_from_seed(seed), must_succeed=False)
    link.note(f"     login {'granted' if d[:3] == bytes([0x67, 0x02, 0x34]) else 'not granted'}")


def rebuild(shadow: bytes) -> tuple[bytes, list[int]]:
    img = bytearray(b"\xff" * 512)
    have = []
    for page, rec in enumerate(PAGE_RECORD):
        if rec is None or page in NOT_TRACKED or (rec + 1) * 16 > len(shadow):
            continue
        img[page * 16:(page + 1) * 16] = shadow[rec * 16:(rec + 1) * 16]
        have.append(page)
    return bytes(img), have


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial port of a dumb K-line cable, e.g. COM8")
    ap.add_argument("out", type=Path, help="rebuilt 512-byte page image")
    ap.add_argument("--shadow", type=lambda s: int(s, 0), default=0x383DA8,
                    help="RAM shadow address (default 0x%(default)X, build-specific)")
    ap.add_argument("--slots", type=int, default=21, help="number of 16-byte record slots")
    args = ap.parse_args()

    link = Link(args.port)
    raw = bytearray()
    try:
        link.wake()
        link.note("ECU identification (1A 9B)")
        ident = link.request(bytes([0x1A, 0x9B]), must_succeed=False)
        if ident[0] == 0x5A:
            link.note("     " + "".join(chr(c) if 32 <= c < 127 else "." for c in ident[2:]))
        link.note("security login")
        try_login(link)
        link.note("development session (10 86)")
        link.request(bytes([0x10, 0x86]))
        link.note("security login in the development session")
        try_login(link)
        link.note(f"reading {args.slots} slots from 0x{args.shadow:06X}")
        for rec in range(args.slots):
            a = args.shadow + rec * 16
            d = link.request(bytes([0x23, (a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF, 16]))
            if d[0] != 0x63 or len(d) < 17:
                raise RuntimeError(f"unexpected read reply for slot {rec}")
            raw += d[1:17]
    finally:
        try:
            link.note("stop communication (82)")
            link.request(bytes([0x82]), must_succeed=False)
        except Exception as e:  # the session times out on its own anyway
            link.note(f"     stop: {e}")
        args.out.with_name(args.out.name + ".log").write_text("\n".join(link.log) + "\n")
        link.close()

    args.out.with_name(args.out.name + ".raw").write_bytes(raw)
    img, have = rebuild(bytes(raw))
    args.out.write_bytes(img)
    missing = sorted(set(range(32)) - set(have))
    print(f"\nwrote {args.out} ({len(have)} pages; not shadowed, written as FF: {missing})")
    print(f"validate with: python me7_95040.py -f {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
