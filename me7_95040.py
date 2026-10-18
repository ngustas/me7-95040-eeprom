#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
me7_95040.py - validate and decode Bosch ME7 95040 (512 byte) EEPROM images.

Page format, confirmed three ways: from four independent dumps, from the
95040tool 0.1 bytecode, and from the page attribute table in the ECU firmware
(see FIRMWARE_FINDINGS.md):

    32 pages x 16 bytes. Bytes 0..13 are payload, bytes 14..15 are a
    little-endian 16-bit checksum:

        minus = 2 if page in BACKUP_PAGES else 1
        cksum = (0xFFFF - (page - minus) - sum(payload)) & 0xFFFF

    The page index is part of the checksum: an otherwise identical payload
    checksums differently depending on which page it sits in.

Structural facts that are NORMAL, not corruption:

  * Pages 0, 17, 18 and 19 carry no checksum. Page 0 is a signature record
    whose last byte is 0x5A; the others are reported as "sentinel".
  * Mirrored pairs are stored from a single RAM copy, so the second page of
    a pair (BACKUP_PAGES) is byte-identical to the first, checksum included.
    It therefore checksums against the PRECEDING page's index. A writer that
    recomputes every page's checksum from its own index will NOT round-trip
    an ECU image byte for byte - the most likely false positive when testing
    EEPROM write support. --canon shows exactly where it diverges.

Some images (e.g. a hand-made virgin) checksum backup pages against their own
index instead. That is self-consistent and reported as "alt-form", but
95040tool would reject it.

Usage:
    me7_95040.py FILE...                 validate + summarise
    me7_95040.py -f [--private] FILE...  also decode named fields
    me7_95040.py -r FILE                 per-page dump
    me7_95040.py -d BASE -r FILE...      mark pages that differ from BASE
    me7_95040.py -c FILE FILE...         line several images up side by side
    me7_95040.py --canon FILE -o OUT     write own-index checksums to OUT
                                         (never in place) and report the delta

Exits 1 if any page fails its checksum for no known reason, else 0.
"""
import sys

# Checked before the remaining imports so an older interpreter gets a clear
# message instead of an ImportError (itertools.batched is new in 3.12).
if sys.version_info < (3, 12):
    sys.exit("me7_95040.py needs Python 3.12 or newer")

import argparse
import hashlib
from enum import StrEnum
from itertools import batched
from pathlib import Path
from typing import NamedTuple

ROW = 16
PAYLOAD = 14
# Page 0 is a signature record, not a checksummed one. Byte 15 is 0x5A in every
# dump examined, virgin and programmed alike.
SIG_ROW, SIG_BYTE = 0, 0x5A

# Authoritative page lists, taken from the 95040tool 0.1 bytecode
# (files.s4wiki.com). Its validateChecksum() is:
#     minus = 2 if pageno in backupPage else 1
#     calcsum = 65535 - (pageno - minus) - bytesum
# which checksum() below implements literally. Both lists are confirmed against
# four dumps, and against ECU code: the page attribute table at 0x816E00 in
# 4Z7907551S 1037367582 has flag bit 0 (checksummed) clear on exactly
# NO_CHECKSUM_PAGES and bit 6 (checksum index = page-1) set on exactly
# BACKUP_PAGES. See FIRMWARE_FINDINGS.md.
NO_CHECKSUM_PAGES = frozenset({0, 17, 18, 19})
BACKUP_PAGES = frozenset({8, 10, 12, 14, 16, 31})

# Page -> RAM shadow record id, from the high byte of each word in that table
# (shadow slot = 0xBDA8 + id*16 on this build). Pages sharing an id are stored
# from one 16-byte RAM copy, which is why mirrored pairs are byte-identical.
# 17/18/19 and 27/28/29 share an id but only the first page of each is kept
# in sync. Page 0 is not shadowed. Taken from one firmware; other builds may
# differ.
PAGE_RECORD = (None, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x06,
               0x07, 0x07, 0x08, 0x08, 0x09, 0x09, 0x0A, 0x0A,
               0x0B, 0x0B, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
               0x11, 0x12, 0x13, 0x13, 0x13, 0x14, 0x14)


class Span(NamedTuple):
    page: int
    start: int
    length: int


# Field map. Spans are concatenated in order.
FIELDS: dict[str, list[Span]] = {
    "immo_flag":    [Span(1, 2, 1), Span(2, 2, 1)],    # both == 1 -> immobiliser on
    "dtc_p0601":    [Span(1, 12, 1), Span(2, 12, 1)],
    "skc":          [Span(3, 2, 2)],                   # little-endian, as decimal
    "cluster_code": [Span(3, 4, 6)],
    "vin":          [Span(11, 5, 5), Span(13, 0, 12)],  # 17 chars across two pages
    "immo_id":      [Span(13, 12, 1), Span(15, 0, 13)],  # 14 chars, starts in page 13
    "part_number":  [Span(28, 2, 12)],                 # see PART_NUMBER_ALT
    "variant":      [Span(29, 0, 4)],
    "tool_stamp":   [Span(30, 2, 6)],
    # Page 0 is the signature record. Derived here, not from 95040tool:
    #   [0:5]  5-char ASCII code, spaces when blank
    #   [6]    0xFF on every dump seen
    #   [9:15] 6-char ASCII date, DDMMYY: the Bosch manufacture date. bporg's
    #          "050703" matches its case label "MOTRONIC 03-07-05" (printed
    #          YY-MM-DD). 2392's "221103" rules out reading it as YYMMDD.
    #   [15]   0x5A ('Z') on every dump seen, programmed or virgin
    "workshop_code": [Span(0, 0, 5)],
    "mfg_date":      [Span(0, 9, 6)],
    # From firmware disassembly (FIRMWARE_FINDINGS.md). The names say only
    # what the code proves; what these values mean is NOT identified.
    #   adapt_p5p6: five LE words 5[2..12], a flag word 5[12], then two words
    #     6[2..6]. These are runtime-learned values that 0x86305E seeds from
    #     flash defaults; module 0x862F00-0x8644FF.
    #   flags_p7: a bitfield at 7[7] whose bits 0-4 are set and cleared
    #     individually by 0x88B5BA.
    "adapt_p5p6": [Span(5, 2, 12), Span(6, 2, 4)],
    "flags_p7":   [Span(7, 7, 1)],
    # Page 30 (and its backup, 31) is the programming record:
    #   [2:8]  tool stamp (above)
    #   [8]    bit 7 = programming flag. NefMoto calls it "P0602"; this
    #          firmware's "programming not complete" check reads it at
    #          0x86C0B6. A programming session with the wrong flash layout
    #          sets it; a full correct-layout read plus an ECU reset clears it
    #          (docs/checksum-no-start.md).
    #   [9:11] counters, not decoded. Byte 10 rose by exactly 6 per full read.
    #   [12:14] lockout, per NefMoto's bootmode docs ("measured on ME7.5").
    "p0602_flag":    [Span(30, 8, 1), Span(31, 8, 1)],
    "prog_counters": [Span(30, 9, 2)],
    "lockout":       [Span(30, 12, 2), Span(31, 12, 2)],
}

# Some images carry the part number on page 20 instead of 28, with the same
# shape (two leading bytes then 12 ASCII). Checked as a fallback.
PART_NUMBER_ALT = [Span(20, 2, 12)]

# Pages that held only zeros in every populated dump examined. An observation,
# not a rule: the firmware writes 22 and 25 (FIRMWARE_FINDINGS.md).
ALWAYS_ZERO = frozenset({22, 25, 26, 27})
PRIVATE = frozenset({"vin", "immo_id", "skc"})
HEX_FIELDS = frozenset({"cluster_code", "immo_flag", "dtc_p0601", "flags_p7",
                        "p0602_flag", "prog_counters", "lockout"})
# Shown as raw values even when all zero: zero is meaningful for these.
ALWAYS_SHOWN = frozenset({"p0602_flag", "prog_counters", "lockout"})

# Row 9 carries the same bytes in every dump examined, across three unrelated
# ECU families and a virgin image, so it makes a handy read-integrity canary.
# It is NOT fixed, though: the firmware writes page 9 at runtime (0x88C468,
# 0x89BF08), and the 0x80 bytes look like neutral defaults. A different value
# is plausible on an adapted ECU. Treat a mismatch as a reason to re-read,
# not as proof the read was bad.
CANARY_ROW = 9
CANARY = bytes.fromhex("0080808080000080008080ff000078fb")


class Status(StrEnum):
    OK = "ok"
    MIRROR = "mirror"
    ERASED = "erased"
    SIG = "signature"
    SENT = "sentinel"
    ALT = "alt-form"
    BAD = "BAD"


def checksum(payload: bytes, page: int, minus: int = 1) -> int:
    """The ECU's checksum; minus=2 for a backup page."""
    return (0xFFFF - (page - minus) - sum(payload)) & 0xFFFF


def stored(row: bytes) -> int:
    return int.from_bytes(row[PAYLOAD:PAYLOAD + 2], "little")


def printable(raw: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in raw)


def meaningful(raw: bytes) -> bool:
    return any(c not in (0, 0x20, 0xFF) for c in raw)


class Image:
    def __init__(self, path: str) -> None:
        self.path = path
        self.data = Path(path).read_bytes()
        self.rows = [self.data[i:i + ROW] for i in range(0, len(self.data), ROW)]
        self.sha = hashlib.sha256(self.data).hexdigest()

    @property
    def name(self) -> str:
        return Path(self.path).name

    def classify(self, n: int) -> Status:
        """Classify one page.

        A backup page normally borrows the preceding page's index (minus=2).
        Some images instead checksum every page against its own index. Both
        are self-consistent, so the second form is reported as alt-form rather
        than as an error - but it will fail 95040tool's validateChecksum.
        """
        row = self.rows[n]
        if row == b"\xff" * ROW:
            return Status.ERASED
        if n in NO_CHECKSUM_PAGES:
            return Status.SIG if n == SIG_ROW else Status.SENT
        got = stored(row)
        own = checksum(row[:PAYLOAD], n, minus=1)
        if n in BACKUP_PAGES:
            if got == checksum(row[:PAYLOAD], n, minus=2):
                return Status.MIRROR
            return Status.ALT if got == own else Status.BAD
        if got == own:
            return Status.OK
        # A sentinel outside the known list: repeated byte pair where a
        # checksum would sit.
        if row[PAYLOAD] == row[PAYLOAD + 1]:
            return Status.SENT
        return Status.BAD

    def statuses(self) -> list[Status]:
        return [self.classify(n) for n in range(len(self.rows))]

    def gather(self, spans: list[Span]) -> bytearray | None:
        raw = bytearray()
        for page, start, length in spans:
            if page >= len(self.rows):
                return None
            raw += self.rows[page][start:start + length]
        return raw

    def field(self, key: str) -> tuple[str, bytearray] | None:
        """Return (text, raw) for a named field, or None if unreadable."""
        raw = self.gather(FIELDS[key])
        if raw is None:
            return None
        if key == "part_number" and not meaningful(raw):
            alt = self.gather(PART_NUMBER_ALT)
            if alt is not None and meaningful(alt):
                raw = alt

        match key:
            case "mfg_date":
                txt = printable(raw)
                if txt.isdigit() and len(txt) == 6:
                    return f"{txt[0:2]}-{txt[2:4]}-20{txt[4:6]} (dd-mm-yy)", raw
                return "(unset)", raw
            case "skc":
                return f"{int.from_bytes(raw[0:2], 'little'):05d}", raw
            case _ if key in HEX_FIELDS:
                return raw.hex(" ").upper(), raw
            case "adapt_p5p6":
                words = (int.from_bytes(bytes(pair), "little") for pair in batched(raw, 2))
                return " ".join(f"{w:04X}" for w in words), raw

        visible = sum(1 for c in raw if 32 <= c < 127)
        # Short fields must be wholly printable; long ones tolerate padding.
        threshold = len(raw) if len(raw) <= 8 else len(raw) * 0.6
        if visible < threshold:
            return "(unset)", raw      # binary noise, not a programmed string
        return "".join(chr(c) for c in raw if 32 <= c < 127).strip(), raw

    def decode(self, show_private: bool = False) -> None:
        print("  fields:")
        for key in FIELDS:
            got = self.field(key)
            if got is None:
                continue
            txt, raw = got
            if key in ALWAYS_SHOWN:
                pass
            elif not txt.strip(".") or set(raw) in ({0}, {0xFF}):
                txt = "(unset)"
            elif key in PRIVATE and not show_private:
                txt = txt[:4] + "*" * max(0, len(txt) - 4) + "  [--private to show]"
            if key == "immo_flag":
                on = raw[0] == raw[1] == 1
                txt += f"   -> immobiliser {'ON' if on else 'OFF'}"
            elif key == "p0602_flag":
                state = {0: "clear", 2: "SET"}.get(sum(b >> 7 for b in raw), "copies DISAGREE")
                txt += f"   -> programming flag (bit 7) {state}"
            elif key == "lockout":
                txt += "   -> none" if not any(raw) else "   -> lockout bytes set"
            print(f"    {key:<13} {txt}")

    def ascii(self, n: int) -> str:
        return printable(self.rows[n])


def tally(img: Image) -> dict[Status, int]:
    st = img.statuses()
    return {k: st.count(k) for k in Status}


def summarise(img: Image) -> None:
    t = tally(img)
    statuses = img.statuses()
    size_note = "" if len(img.data) == 512 else "  !! expected 512 bytes"
    print(img.name)
    print(f"  {len(img.data)} bytes{size_note}   sha256 {img.sha}")
    print(f"  rows: {t[Status.OK]} ok, {t[Status.MIRROR]} backup, "
          f"{t[Status.ALT]} alt-form, {t[Status.ERASED]} erased, "
          f"{t[Status.SIG]} signature, {t[Status.SENT]} sentinel, "
          f"{t[Status.BAD]} BAD")
    off_list_sentinel = any(st == Status.SENT and n not in NO_CHECKSUM_PAGES
                            for n, st in enumerate(statuses))
    if t[Status.ALT] or off_list_sentinel:
        print("  note: deviates from 95040tool's page model; that tool would "
              "reject it")
    if len(img.rows) > CANARY_ROW:
        got = img.rows[CANARY_ROW]
        if got == CANARY:
            print(f"  row {CANARY_ROW} canary: ok")
        else:
            print(f"  row {CANARY_ROW} canary: DIFFERS -> {got.hex(' ')}")
            print("     (differs from the common value; re-read to rule out a "
                  "bad transfer - page 9 can legitimately change on an "
                  "adapted ECU)")
    if bad := [n for n, st in enumerate(statuses) if st == Status.BAD]:
        print(f"  !! unexplained checksum failures at rows {bad}")
    else:
        print("  no unexplained checksum failures")


def dump_rows(img: Image, base: Image | None = None) -> None:
    print(f"\n{img.name}")
    hdr = f"{'row':>3} {'off':>6}  {'payload (14B)':<42} {'cksum':<6} {'status':<8} ascii"
    print(hdr)
    print("-" * len(hdr))
    for n, row in enumerate(img.rows):
        mark = " *" if base is not None and n < len(base.rows) and base.rows[n] != row else ""
        hexs = " ".join(f"{b:02x}" for b in row[:PAYLOAD])
        print(f"{n:>3} 0x{n * ROW:04x}  {hexs:<42} 0x{stored(row):04x} "
              f"{img.classify(n):<8} |{img.ascii(n)}|{mark}")


def compare(imgs: list[Image]) -> None:
    """Line up every row across several images."""
    labels = [i.name[:18] for i in imgs]
    print(f"{'row':>3} {'off':>6}  " + "  ".join(f"{l:<18}" for l in labels))
    print(f"{'':>3} {'':>6}  " + "  ".join(f"{'(status)':<18}" for _ in labels))
    print("-" * (11 + 20 * len(imgs)))
    for n in range(max(len(i.rows) for i in imgs)):
        cells: list[str] = []
        stats: list[str] = []
        for img in imgs:
            if n < len(img.rows):
                cells.append(img.ascii(n))
                stats.append(img.classify(n))
            else:
                cells.append("-" * 16)
                stats.append("-")
        flag = "" if len(set(cells)) == 1 else "  <-- differs"
        print(f"{n:>3} 0x{n * ROW:04x}  " + "  ".join(f"{c:<18}" for c in cells) + flag)
        print(f"{'':>3} {'':>6}  " + "  ".join(f"{s:<18}" for s in stats))


def canon(img: Image, out: str) -> None:
    """Rewrite every row's checksum against its own index; report what changes."""
    buf = bytearray(img.data)
    changed = []
    for n, row in enumerate(img.rows):
        if img.classify(n) in (Status.ERASED, Status.SIG, Status.SENT):
            continue
        want = checksum(row[:PAYLOAD], n, minus=1)
        if stored(row) != want:
            buf[n * ROW + PAYLOAD:n * ROW + ROW] = want.to_bytes(2, "little")
            changed.append(n)
    Path(out).write_bytes(buf)
    print(f"wrote {out}")
    print(f"  rows rewritten: {changed or 'none'}")
    print(f"  sha256 before {img.sha}")
    print(f"  sha256 after  {hashlib.sha256(buf).hexdigest()}")
    if changed:
        print("  ^ these are the rows where a per-row-recomputing writer")
        print("    diverges from what the ECU actually stores.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("-r", "--rows", action="store_true", help="per-row dump")
    ap.add_argument("-d", "--diff", metavar="BASE", help="mark rows differing from BASE")
    ap.add_argument("-f", "--fields", action="store_true", help="decode named fields")
    ap.add_argument("--private", action="store_true",
                    help="show VIN / immo ID / SKC in full")
    ap.add_argument("-c", "--compare", action="store_true",
                    help="line up all rows across several images")
    ap.add_argument("--canon", action="store_true",
                    help="rewrite checksums against each page's own index")
    ap.add_argument("-o", "--out", help="output file for --canon")
    args = ap.parse_args()

    base = Image(args.diff) if args.diff else None
    imgs = [Image(f) for f in args.files]

    if args.compare:
        compare(imgs)
        return 0

    if args.canon:
        if len(imgs) != 1 or not args.out:
            ap.error("--canon takes exactly one input and requires -o OUT")
        canon(imgs[0], args.out)
        return 0

    worst = 0
    for img in imgs:
        summarise(img)
        if tally(img)[Status.BAD]:
            worst = 1
        if args.fields:
            img.decode(args.private)
        if args.rows:
            dump_rows(img, base)
        print()
    return worst


if __name__ == "__main__":
    sys.exit(main())
