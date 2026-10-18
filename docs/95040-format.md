# ME7 95040 EEPROM image format

A 95040 image is 512 bytes: **32 pages of 16 bytes**. This document describes
the ME7 layout, as confirmed on ME7.1.1 (`4Z7907551S`, software `1037367582`)
and checked against ME7.5 dumps.

Sources, in order of authority:

1. **ECU firmware.** The page attribute table and EEPROM routines in
   `1037367582`. See [FIRMWARE_FINDINGS.md](../FIRMWARE_FINDINGS.md).
2. **95040tool 0.1.** Its Python 2.7 bytecode was recovered with
   `tools/pyc27.py`. See [prior-art-tools.md](prior-art-tools.md).
3. **Four real dumps.** An ME7.1.1 2.7T, an ME7.5 1.8T (AWU), a third ECU
   (part `8E0909018A`) and a virgin template.

Firmware addresses are for this one build. Other builds will move them, but the
structure should be the same.

## Page structure and checksum

```
bytes 0..13   payload
bytes 14..15  checksum, little-endian 16-bit

minus = 2 if page in BACKUP_PAGES else 1
cksum = (0xFFFF - (page - minus) - sum(payload)) & 0xFFFF
```

The page index is part of the checksum, so the same payload checksums
differently depending on which page holds it.

| List | Pages | Firmware evidence |
|---|---|---|
| No checksum | `0, 17, 18, 19` | page table flag bit 0 clear |
| Backup page (checksum uses `page-1`) | `8, 10, 12, 14, 16, 31` | page table flag bit 6 set |

### Why backup pages borrow the previous index

Each page maps to a record id, and each record id to a 16-byte RAM shadow slot
(`0xBDA8 + id*16`). Both pages of a mirrored pair share one record id. A
background task compares each page with its slot and rewrites the page when
they differ. Both pages are therefore always written from the same 16 bytes,
checksum included.

**Consequence for writers:** recomputing a backup page's checksum from its own
index gives a self-consistent image that is *not* byte-identical to what the
ECU stores. `me7_95040.py --canon` shows the delta.

A virgin template examined did exactly this on page 14. The tool reports it as
`alt-form`. 95040tool rejects it.

## Page map

`rec` is the RAM record id from the page attribute table. "Swept" means the
background task keeps the page in sync with RAM.

| Page | rec | Checksum | Contents | Confidence |
|---|---|---|---|---|
| 0 | — | no | **Signature.** `[0:5]` ASCII workshop code (spaces when blank), `[6]` always `0xFF`, `[9:15]` ASCII **manufacture date DDMMYY**, `[15]` always `0x5A` | high |
| 1 | 0x00 | yes | `[0:2]` header `05 01`; `[2]` **immobiliser flag**; `[10:12]` immobiliser state code; `[12]` **P0601 DTC** | high |
| 2 | 0x01 | yes | Same layout as page 1; the application writes both. Pages 1 and 2 are separate records, not a mirrored pair | high |
| 3 | 0x02 | yes | `[2:4]` **SKC** (LE, decimal); `[4:10]` **cluster code** | high |
| 4 | 0x03 | yes | Same layout as page 3 | high |
| 5 | 0x04 | yes | Runtime-learned words `[2:12]` plus flag word `[12:14]`, seeded from flash defaults. Owning module `0x862F00–0x8644FF`; meaning unknown | structure high |
| 6 | 0x05 | yes | Learned words `[2:6]` (same module); `[8:10]` and `[10]` from a different routine | structure high |
| 7/8 | 0x06 | yes / backup | One record. `[7]` is a latch bitfield, bits 0–4 set and cleared individually | structure high |
| 9/10 | 0x07 | yes / backup | Written at runtime; mostly `0x80` neutral defaults. Identical in all four dumps | structure high |
| 11/12 | 0x08 | yes / backup | `[5:10]` **VIN** chars 1–5 | high |
| 13/14 | 0x09 | yes / backup | `[0:12]` **VIN** chars 6–17; `[12]` first char of **immobiliser ID** | high |
| 15/16 | 0x0A | yes / backup | `[0:13]` **immobiliser ID** chars 2–14 | high |
| 17 | 0x0B | no | Immobiliser-area counters `[6]`, `[7]` (saturate at `0x7F`, `0x80` = set) | medium |
| 18/19 | 0x0B | no | Not swept; no application access found. Populated in one dump, probably by a tester | unknown |
| 20 | 0x0C | yes | **Alternate part-number slot**: 2 bytes + 12 ASCII (used by `8E0909018A`) | high |
| 21 | 0x0D | yes | `[8:14]` start of a byte array that continues on page 22 | structure |
| 22 | 0x0E | yes | `[0:5]` continuation of page 21's array | structure |
| 23 | 0x0F | yes | Holds data in two dumps; no reference found | unknown |
| 24 | 0x10 | yes | `[0]`, `[1]` bytes mirrored from RAM `0x384005` / `0x384004` | structure |
| 25 | 0x11 | yes | Written by `0x8C1EAA` / `0x8C22B6`; `[7]` read | structure |
| 26 | 0x12 | yes | No reference found | unknown |
| 27 | 0x13 | yes | Head of record 0x13 (zeros) | — |
| 28 | 0x13 | yes | `[2:14]` **VAG part number** (not swept; factory/tester data) | high |
| 29 | 0x13 | yes | `[0:4]` **variant** (e.g. `0010`) | high |
| 30/31 | 0x14 | yes / backup | `[2:8]` **tool / workshop stamp** (e.g. `NEFMTO`) | high |

### Notes on specific fields

- **Immobiliser flag.** If both 1[2] and 2[2] are `0x01`, the immobiliser is on.
  On the reference ECU it reads ON. Its immo-off lives in the **flash** tune,
  not the EEPROM, so EEPROM writes do not disturb it.
- **VIN.** 17 characters split 5 + 12 across pages 11 and 13. Byte 13[12] is
  *not* part of the VIN: it is the first character of the 14-character
  immobiliser ID (format `AUZ7Z0xxxxxxxx`).
- **Manufacture date.** Stored as DDMMYY. `050703` on the reference ECU matches
  the case label `MOTRONIC 03-07-05`, which is printed YY-MM-DD. Another dump's
  `221103` rules out reading the EEPROM value as YYMMDD.
- **Part number.** Check page 28 first, then page 20.
- **Virgin images.** A virgin template fills text fields with `X`
  (`0x58`) placeholders. One "virginised" ECU dump had VIN *and* immobiliser
  ID reset to `X`s while keeping its part number.

## Read-integrity canary

Page 9 was byte-identical in every dump examined, across three ECU families
and a virgin:

```
00 80 80 80 80 00 00 80 00 80 80 ff 00 00 78 fb
```

A different value after a bootmode read is a reason to re-read and rule out the
transfer. It is not proof of a bad read, because the firmware does write
page 9.

## Related tools

- `me7_95040.py -f` decodes every high-confidence field above.
- `tools/me7_flash_info.py --table` dumps the page attribute table from a
  flash image, so this map can be checked against another build.
