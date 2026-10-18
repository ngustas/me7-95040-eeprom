# ME7 95040 EEPROM — tools and notes

Tools and reverse-engineering notes from preparing a Bosch ME7.1.1 ECU as a
remote bench unit for work on the
[NefMoto Open Source ECU Flasher](https://github.com/NefMoto/NefMotoOpenSource)
(bootmode EEPROM support, PR #136).

The centre of it is a complete description of the ME7 **95040 EEPROM image
format**, confirmed three independent ways: from four real dumps, from the
recovered source of an older community tool, and from the ECU firmware itself.
The repo also has a validator/decoder for it.

## The reference ECU

| | |
|---|---|
| VAG part number | `4Z7 907 551 S` — `BENZIN ME7.1.1`, variant `0010` |
| Bosch hardware | `0 261 208 288` |
| Software | `1037367582` (ident `242/1/ME7.1.1/5/6030.03//25A/Dst47o/090403//`) |
| Manufactured | 2003-07-05 (case label `MOTRONIC 03-07-05`; EEPROM page 0 stores `050703`) |
| Flash | 1 MB, mapped at `0x800000` |
| EEPROM | ST 95040 (512 B) on the C167 SSC, chip select **P6.3** (`P6` = `0xFFCC`, `DP6` = `0xFFCE`) |
| Donor car | 2004 Audi A6 2.7T, 6-speed manual |

The `4Z7` prefix is the part's originating application (allroad). It does not
mean the donor car was an allroad: late C5 A6 2.7Ts used it as well.

## What's here

| Path | What it is |
|---|---|
| [`me7_95040.py`](me7_95040.py) | Validate and decode 95040 images: checksums, backup pages, named fields, side-by-side comparison, round-trip check |
| [`tools/me7_flash_info.py`](tools/me7_flash_info.py) | Identify an ME7 flash image and dump its EEPROM page attribute table |
| [`tools/me7_kwp_shadow.py`](tools/me7_kwp_shadow.py) | Read the EEPROM from a running ECU over KWP2000 (K-line, slow init `0x11`), without opening it. Read-only. `--mirror` gives all 32 pages |
| [`tools/pyc27.py`](tools/pyc27.py) | Read and disassemble Python 2.7 `.pyc` files from Python 3. This is how 95040tool's logic was recovered |
| [`docs/95040-format.md`](docs/95040-format.md) | **The format reference**: checksum, page lists, full 32-page map, field offsets |
| [`docs/checksum-no-start.md`](docs/checksum-no-start.md) | **Case study**: how a tune with an incomplete checksum caused a no-start after a few key cycles, and the P1681 patch that fixed it |
| [`docs/immo-off.md`](docs/immo-off.md) | Turning the immobiliser off in the 95040, with sources, a worked example and this ECU's status |
| [`FIRMWARE_FINDINGS.md`](FIRMWARE_FINDINGS.md) | Ghidra disassembly of the 1037367582 firmware: EEPROM driver, page table, RAM shadow, per-page owners |
| [`docs/prior-art-tools.md`](docs/prior-art-tools.md) | What 95040tool 0.1, ME7EEPROM 1.40 and me7_95040 1.31 actually do |
| [`docs/bench-harness.md`](docs/bench-harness.md) | **Wiring**: 121-pin connector pinout for this ECU, the minimum bench circuit, boot-mode tap, pre-power-up checks |
| [`docs/remote-bench.md`](docs/remote-bench.md) | How to set up the ECU for remote bench access |
| [`ghidra_scripts/`](ghidra_scripts/) | The Ghidra (Java) scripts used for the firmware analysis |

## Quick start

All the scripts need **Python 3.12+**. Only `me7_kwp_shadow.py` needs
anything else: `pyserial`. Each script has a
[PEP 723](https://peps.python.org/pep-0723/) header, so `uv run` works as well.

```bash
python me7_95040.py dump.bin                     # validate + summarise
python me7_95040.py -f dump.bin                  # decode fields (VIN/immo ID/SKC masked)
python me7_95040.py -f --private dump.bin        # ...unmasked
python me7_95040.py -r dump.bin                  # per-page dump with status
python me7_95040.py -c a.bin b.bin c.bin         # compare images side by side
python me7_95040.py --canon dump.bin -o out.bin  # show where a naive writer diverges
python tools/me7_flash_info.py flash.bin --table # idents + EEPROM page table
python tools/me7_kwp_shadow.py COM8 live.bin --mirror  # full EEPROM from a running ECU
```

`me7_95040.py` exits with 1 if any page fails its checksum for no known
reason, so it can be dropped into a test script.

## Key findings

- **The checksum includes the page index.**
  `cksum = (0xFFFF - (page - minus) - sum(payload)) & 0xFFFF`, stored
  little-endian at bytes 14–15. `minus` is 2 on backup pages and 1 everywhere
  else.
- **The page lists are fixed and come from the firmware.** Pages `0, 17, 18, 19`
  have no checksum. Pages `8, 10, 12, 14, 16, 31` are backup pages. Both lists
  come straight from the page attribute table at `0x816E00` (flag bits 0 and 6).
- **Watch for the round-trip trap.** The ECU writes both pages of a mirrored
  pair from a single RAM copy, so the backup page carries the *first* page's
  checksum. A writer that recomputes every checksum from the page's own index
  produces a valid but **different** image. A plain hash comparison will then
  report a failed write when nothing went wrong. Run `--canon` to see exactly
  where (pages 8, 10, 12, 14, 16 and 31).
- **Firmware supports two address widths.** The EEPROM driver has both a
  9-bit form (95040) and a 16-bit form (95080 and up), selected by RAM flag
  `0xFDB4` bit 2. This is directly relevant to multi-chip bootmode support.
- **Pages 5/6 are learned values**, seeded from flash defaults. They are not
  factory calibration, even though a virgin chip already holds them.
- **The part number may be on page 20 instead of 28**, depending on the image.
  A decoder that reads only page 28 will come back empty on some ECUs.
- **Page 9 isn't constant.** It is identical across every dump examined, which
  makes it a useful canary for a bad read. The firmware does write it at
  runtime, though, so treat a mismatch as a prompt to re-read.

- **A tune that passes every sum can still fail the RSA check.** On this ECU,
  a tuning tool corrected all the additive checksums but didn't re-sign the
  MD5. The ECU then refused to start after a couple of key cycles. The fix
  used was the one-byte P1681 patch at `0x86C0B6`, which skips the check of
  EEPROM page 30 byte 8 bit 7. See
  [`docs/checksum-no-start.md`](docs/checksum-no-start.md).

- **This ECU answers KW1281 at slow-init address `0x01` and KWP2000 only at
  `0x11`.** Old tools that wake the ECU at `0x01` (ME7EEPROM, me7_95040) can't
  read it over OBD. Current NefMoto retries at `0x11`.
- **A full EEPROM image needs no bootmode.** The ECU mirrors the chip at
  `0x600000` and serves every page except 3 and 4 (the SKC and cluster code),
  which the RAM shadow supplies. `me7_kwp_shadow.py --mirror` combines them.
- **Live state (2026-10-18):** the flash is `Fixed.bin` (the ME7Sum-repaired
  v0.08, with the P1681 patch), and the immobiliser is off in the EEPROM. The
  "programming not complete" bit (page 30 byte 8 bit 7) **was set** that
  morning and **cleared** after a programming-session flash read completed.
  See [`docs/checksum-no-start.md`](docs/checksum-no-start.md).

Still unidentified: what the values on pages 5/6, 7/8, 9/10 and 21–25 *mean*
(their layout and owning code are known), pages 18/19/23/26, and attribute flag
bits 2/4/5. These are deliberately left blank in the tool rather than guessed.

## Not included

There are **no `.bin` files** in this repo, and `.gitignore` blocks them:

- EEPROM dumps contain the VIN, the immobiliser ID and the SKC (the key code).
- Flash images are Bosch firmware.

Keep both offline. The tool masks VIN, immobiliser ID and SKC by default.

## Relevance to NefMoto PR #136

PR #136 added an `ME7.1.1 P6.3` chip-select preset, and this ECU uses exactly
that path. An independent cross-reference is the port table embedded in the
older ME7EEPROM 1.40: P6 is at `0xFFCC` with its direction register at `0xFFCE`.
ME7EEPROM 1.40 also supports a `95P08` part, which the PR's device catalog does
not list. See [`docs/prior-art-tools.md`](docs/prior-art-tools.md).
