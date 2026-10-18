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

**Settled by a live read (2026-10-18): the immobiliser is OFF in this ECU's
EEPROM.**

The EEPROM contents were read from the running ECU's RAM shadow over
KWP2000 with [`tools/me7_kwp_shadow.py`](../tools/me7_kwp_shadow.py), without
opening the ECU. The rebuilt page image validates cleanly, and:

```
         0x12  0x1E/1F     0x22  0x2E/2F
2013     01    31 fc       01    30 fc      bporg95040.bin: immobiliser on
now      02    30 fc       02    2f fc      live read: immobiliser OFF
```

The live bytes match the worked example above exactly, checksums included.
The immo-off was therefore done in the EEPROM, at some point after the 2013
dump. That 2013 dump is still the only *file* of this ECU's EEPROM: the
tuning files and machine backups were searched, every 512-byte file was
matched against this ECU's VIN and immobiliser ID, and only copies of it
turned up. So the modified image was never saved. One clue to when it
happened: on 2020-12-21, this ECU's 2013 dump, the virgin template, the
"ME7.1.1 OFF" image and `2392.bin` were gathered together on one machine.

Other points:

- None of the 15 distinct flash images on file contains a **code change aimed
  at the immobiliser**. The only code patch is the one-byte P1681 fix (see
  [checksum-no-start.md](checksum-no-start.md)).
- The live read covers pages 1–17, 20–27 and 30–31. Page 0, 18, 19, 28 and 29
  aren't held in RAM, so a full chip image still needs a bootmode read.

On a bench the immobiliser only blocks the engine from starting. Diagnostics,
flashing and bootmode access work either way, so the remote-bench setup
doesn't depend on it.
