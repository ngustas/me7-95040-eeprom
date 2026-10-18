# Immobiliser off in the 95040 EEPROM

How ME7 stores the immobiliser state in the 95040, how to turn it off there,
and what is known about the reference ECU (`4Z7907551S`, software
`1037367582`).

## The flag

| EEPROM offset | Page / byte | Value |
|---|---|---|
| `0x12` | page 1, byte 2 | `01` = immobiliser **on** · `02` = **off** |
| `0x22` | page 2, byte 2 | same; must match `0x12` |

Each page's checksum is at bytes 14–15 (`0x1E/1F` and `0x2E/2F`), and **each
must be recomputed after the change**. Pages 1 and 2 are separate records,
not a mirrored pair, so each is checksummed with its own index
(`minus = 1`, see [95040-format.md](95040-format.md)). Page 2's checksum
therefore can't be copied from page 1.

### Sources

- **95040tool 0.1** (bytecode recovered with `tools/pyc27.py`). `setImmo()`
  writes `data[1][2] = data[2][2] = 1` to turn the immobiliser on and `= 2` to
  turn it off, then fixes the checksums when saving. `parse()` reports
  "on" only when both bytes are `1`.
- **ECU firmware, from code.** The immobiliser block loads the word at
  page 1 bytes 2–3, or page 2 bytes 2–3 (`mov r4,[0xBDAA]` at `0x883462`,
  `mov r4,[0xBDBA]` at `0x883494`), into an immobiliser state variable at RAM
  `0xA0AA`. The block then tests that state against several values,
  including `2` (`cmp r4,#2` at `0x883B0A`). The ECU can also write the flag
  itself through its generic field writer (`0x883A68`, `0x8A5AC6`). The full
  state machine hasn't been traced. The firmware evidence shows that the
  EEPROM byte *seeds* the immobiliser state; it doesn't independently prove
  what `2` means.
- **Images.** A virgin template reads `02 02`: a new ECU with the immobiliser
  not yet active. A different ME7.1.1 ECU's EEPROM labelled "ME7.1.1 OFF"
  also reads `02 02`, with its VIN reset to `X` placeholders. Every programmed
  ECU dump examined reads `01 01`.

## Worked example (reference ECU)

```
         0x12  0x1E/1F     0x22  0x2E/2F
on       01    31 fc       01    30 fc      <- the 2013 dump of this ECU
off      02    30 fc       02    2f fc
```

Both images validate with `me7_95040.py`. `-f` shows the result on the
`immo_flag` line.

Read the EEPROM in bootmode, keep the original, write the modified image back,
then read it again and validate it. The row 9 canary and the checksum report
will catch a bad transfer.

## Status of the reference ECU

- The **only** EEPROM image of this ECU on file is `bporg95040.bin`
  (2013-10-20). It reads **`01 01` — immobiliser on**. All tuning files and
  the machine backups were searched for it: every 512-byte file was matched
  against this ECU's VIN and immobiliser ID, and only copies of that one dump
  turned up.
- If the immobiliser was later turned off in the EEPROM, the resulting image
  was not kept. One clue: on 2020-12-21, four
  95040 images were gathered together on one machine. They were this ECU's
  2013 dump, the virgin template, the "ME7.1.1 OFF" image and `2392.bin`.
  That is consistent with preparing an EEPROM immo-off at that point.
- None of the 15 distinct flash images on file contains a **code change aimed at
  the immobiliser**. The only code patch is the one-byte P1681 fix (see
  [checksum-no-start.md](checksum-no-start.md)). A calibration-level immo
  setting can't be ruled out without map definitions for this software.
- **To settle it:** read the ECU's EEPROM in bootmode and run
  `python me7_95040.py -f dump.bin`.

On a bench the immobiliser only blocks the engine from starting. Diagnostics,
flashing and bootmode access work either way, so the remote-bench setup
doesn't depend on it.
