#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
me7_flash_info.py - identify an ME7 flash image and dump its EEPROM page table.

Prints the Bosch ident strings (ME7 variant, VAG part number, Bosch hardware
and software numbers) and, optionally, the EEPROM page attribute table.

The page attribute table holds one 16-bit word per EEPROM page:
    word = (record_id << 8) | flags
    flags bit 0  page carries a checksum
          bit 1  page is shadowed in RAM and kept in sync
          bit 6  second copy of a pair: checksums against page-1
          bit 7  member of a mirrored pair
          bits 2, 4, 5 not identified

Its address is BUILD-SPECIFIC. 0x816E00 is correct for 4Z7907551S software
1037367582 (see FIRMWARE_FINDINGS.md); other builds will move it. The tool
sanity-checks the table and warns when it does not look right.

Usage:
    me7_flash_info.py FLASH.bin
    me7_flash_info.py FLASH.bin --table [--table-addr 0x816E00]
"""
import sys

if sys.version_info < (3, 12):
    sys.exit("me7_flash_info.py needs Python 3.12 or newer")

import argparse
import hashlib
import re
from pathlib import Path

FLASH_BASE = 0x800000
DEFAULT_TABLE = 0x816E00
PAGES = 32

IDENT_PATTERNS = [
    ("bosch ident", re.compile(rb"\d{3}/\d/ME7[.\d]*/[ -~]{8,60}")),
    ("vag part / engine", re.compile(rb"[0-9][A-Z0-9]{2}9\d{5}[A-Z]{0,2} {1,3}\d\.\dL[ -~]{3,30}")),
    ("hw / sw numbers", re.compile(rb"0261\d{6}1037\d{6}[ -~]{0,12}")),
]


def idents(data: bytes) -> list[tuple[str, int, str]]:
    out = []
    for label, pat in IDENT_PATTERNS:
        for m in pat.finditer(data):
            out.append((label, FLASH_BASE + m.start(), m.group().decode("ascii", "replace").rstrip()))
    return out


def page_table(data: bytes, addr: int) -> list[int]:
    off = addr - FLASH_BASE
    if not 0 <= off <= len(data) - PAGES * 2:
        raise SystemExit(f"table address 0x{addr:06X} is outside the image")
    return [int.from_bytes(data[off + 2 * p:off + 2 * p + 2], "little") for p in range(PAGES)]


def looks_like_table(words: list[int]) -> bool:
    """Record ids should be non-decreasing apart from page 0's 0xFF."""
    ids = [w >> 8 for w in words[1:]]
    return all(b >= a for a, b in zip(ids, ids[1:])) and ids[-1] < 0x40


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flash", type=Path)
    ap.add_argument("--table", action="store_true", help="dump the EEPROM page table")
    ap.add_argument("--table-addr", type=lambda s: int(s, 0), default=DEFAULT_TABLE,
                    help="table address (default 0x%(default)X, build-specific)")
    args = ap.parse_args()

    data = args.flash.read_bytes()
    print(f"{args.flash.name}  {len(data)} bytes")
    print(f"  md5    {hashlib.md5(data).hexdigest()}")
    print(f"  sha256 {hashlib.sha256(data).hexdigest()}")
    found = idents(data)
    for label, addr, text in found:
        print(f"  {label:<18} 0x{addr:06X}  {text}")
    if not found:
        print("  no ME7 ident strings found - is this an ME7 flash image?")

    if not args.table:
        return 0

    words = page_table(data, args.table_addr)
    print(f"\nEEPROM page table @ 0x{args.table_addr:06X}")
    if not looks_like_table(words):
        print("  !! this does not look like a page table; the address is probably "
              "wrong for this build")
    print("  page  word  rec  flags     cksum backup pair shadow")
    for p, w in enumerate(words):
        f = w & 0xFF
        print(f"  {p:>4}  {w:04X}  {w >> 8:>3}  {f:08b}  "
              f"{'y' if f & 0x01 else '-':>5} {'y' if f & 0x40 else '-':>6} "
              f"{'y' if f & 0x80 else '-':>4} {'y' if f & 0x02 else '-':>6}")
    no_ck = [p for p, w in enumerate(words) if not w & 0x01]
    backup = [p for p, w in enumerate(words) if w & 0x40]
    print(f"  no-checksum pages: {no_ck}")
    print(f"  backup pages:      {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
