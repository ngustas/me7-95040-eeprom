# The checksum no-start: what happened and how it was fixed

The reference ECU (`4Z7907551S`, software `1037367582`) went through a
classic ME7 failure. An image with a bad checksum started normally, then
**refused to start after a couple of key cycles**. It was fixed by patching
the flash.

This document reconstructs the history from all 15 distinct saved images of the tune:
exported files, a readout taken from the car, versions recovered from a
WinOLS project, and two ME7Sum-repaired files.

Over the life of the tune there were **two separate checksum gaps**:

- **A. Before the patch (May 2018).** The image actually on the car had a
  **wrong main data checksum**. The same day it was read out, the
  "programming not complete" error was fixed with a one-byte P1681 patch.
- **B. After the patch.** The next few versions were saved without
  re-signing the **RSA** signature. The last of them was then repaired with
  **ME7Sum**.

What is **proven** below is marked as such. What is **inferred** is marked
too.

## 1. ME7 checks its own flash in many ways

ME7Sum (nyetwurk) finds **72 separate checks** in this firmware. All of them
must pass:

| Check | What it covers |
|---|---|
| ROMSYS additive sums | Startup section, all-param page, program pages |
| CRC tables | Fixed tables in the image |
| **RSA signature** | An MD5 over four calibration ranges (`0x10002–0x13FFE`, `0x14382–0x17F4E`, `0x18192–0x1FBDC`, `0x26A00–0x2FFFC`), signed with RSA (exponent 3). Signature at `0xA9C28`, modulus at `0x16A8A` |
| **Main data checksum** | A **byte** sum over the same four ranges, stored at `0xAA46E` with its complement |
| Background checksums | Code ranges re-summed while the engine runs |
| Main program checksum | `0x020000–0x0FFFFF` |
| Multipoint checksums | 66 blocks of 16 KB across the whole image |

A tuning tool has to correct every one of these after a map edit. RSA can't
be re-signed with Bosch's key. Tools get around this by putting a **new
modulus** in the image, from a key pair whose private half they hold, and
signing the new MD5 with it. The ECU reads the modulus from the image, so it
accepts the substitute.

The modulus therefore shows which tool signed an image:

- **Stock key** (`a7f24715…`): untouched.
- **One fixed key** (`05915e15…`): the WinOLS checksum module. It was the
  same key on every WinOLS save in 2013, 2016 and 2018.
- **A different key every time**: ME7Sum, which generates a new random key
  on each run (`srand(time(NULL))` in its `rsa.c`).

## 2. The full version history (proven)

Every image was checked with ME7Sum, built from source (see
[Reproducing](#reproducing)).

| Version | Source | Date | ME7Sum | Key | P1681 patch |
|---|---|---|---|---|---|
| Original | export | 2013-10-19 | 0 errors | stock | — |
| v0.01 load bump | export | 2013-10-20 | 0 errors | WinOLS | — |
| v0.02 mild tune | export | 2013-10-20 | 0 errors | WinOLS | — |
| v0.02.1 mild, numb cats | laptop export | 2016-07-06 | 0 errors | WinOLS | — |
| v0.02.2 mild, cats and O2 off | laptop export | 2016-07-06 | 0 errors | WinOLS | — |
| v0.03 HOT tune | WinOLS project | by 2016-07-06 | 0 errors | WinOLS | — |
| v0.04 HOT tune | WinOLS project | by 2016-07-06 | 0 errors | WinOLS | — |
| **Readout of the car** ("existing mild tune") | ECU read | 2018-05-10 | **1 error: main data checksum** | WinOLS | — |
| v0.05 HOT tune, "fix for programming not complete" | export | 2018-05-10 | 0 errors | WinOLS | **yes** |
| v0.06 (two variants), v0.07, v0.08 (three identical files, including the "checksum test") | export | 2018-05-11 to 14 | **1 error: RSA** | WinOLS | yes |
| **Fixed.bin**, **fudge.bin** (= v0.08) | ME7Sum output | 2018-05-14 | **0 errors** | **ME7Sum, two different keys** | yes |

v0.03 and v0.04 were never exported. They were carved out of the WinOLS
project file, which stores each version as a raw 1 MB image at a fixed
stride. The carving is exact: the v0.01 and v0.02 images carved from the
same project are byte-identical to their exported files.

## 3. Gap A: the image on the car had a wrong main checksum (proven)

The readout taken from the car on 2018-05-10 has **exactly the same
calibration as v0.02.1**. It differs from the clean v0.02.1 export in only
6 bytes, all in the main data checksum slot:

```
0xAA46E  car readout:  1f 36 07 00  e0 c9 f8 ff   -> 0x0007361F (+ complement)
         v0.02.1:      6b 7c a6 00  94 83 59 ff   -> 0x00A67C6B (correct)
```

- The car's sum and complement agree with each other. A tool **wrote** that
  value deliberately; this isn't random corruption.
- The correct value is the byte sum of the four ranges. The stored value is
  about 1/23 of it, but it doesn't match any partial or truncated byte or
  word sum over those ranges. Exactly how it was miscalculated **can't be
  reproduced**.
### What the files prove

- **The readout is a raw read of the car, not a merge.** Apart from those
  6 bytes it matches v0.02.1 exactly: calibration, **RSA signature**,
  multipoint checksum table and program checksum. Every WinOLS save on file
  has a correct main checksum, so a WinOLS merge would have fixed it; a raw
  read keeps whatever was flashed.
- **Every edit needed the main checksum, not just the cat edit.** All of the
  changes sit inside the main-checksum/MD5 ranges, and every saved file carries
  a correct main checksum:

  | Edit | Range 1 | Range 2 | Range 3 | Range 4 | Outside | Main checksum in file |
  |---|---|---|---|---|---|---|
  | stock → v0.01 (load bump) | 0 | 0 | 0 | 30 | 0 | `0x00A6799B` ✓ |
  | v0.01 → v0.02 (mild tune) | 1 | 26 | 0 | 89 | 0 | `0x00A67BF8` ✓ |
  | v0.02 → v0.02.1 (numb cats) | 0 | 0 | **4** | 0 | 0 | `0x00A67C6B` ✓ |
  | v0.02 → v0.02.2 (cats/O2 off) | 0 | 0 | **12** | 0 | 0 | `0x00A67C42` ✓ |
  | v0.02 → v0.03 | 274 | 446 | 136 | 61 | 0 | `0x00A662CC` ✓ |

  The power tune (stock → v0.02: 146 bytes in ranges 1, 2 and 4) required a
  new main checksum and RSA signature as much as the cat edit did, got correct
  ones, and flashed fine in 2013. The cat edit's 4 bytes are `0x8188F1–F3`
  (`9a fd fd` → `ff ff ff`) and `0x81A2D9` (`46` → `50`).

  **What *is* different about it:** it was the **first flashed edit in
  range 3**. v0.02 never touched range 3; v0.02.1 did, and its flashed main
  checksum came out wrong. That's **only suggestive** of whatever computed the
  bad value mishandling range 3. `0x0007361F` is smaller than the byte sum of
  any single range (the smallest is about `0x128E89`), so it isn't simply
  "the sum without range 3" either.
- **The bad value was inside the image that was flashed.** The readout's
  program-area checksums (RSA signature, program checksum) are v0.02.1's, so
  the program area was written; this wasn't a data-only write that left an
  old checksum behind. The wrong main checksum (`0xAA46E`) is in the **same
  64 KB sector, `0x8A0000`, as the correct RSA signature** (`0xA9C28`), and
  that sector is the only one where the car differs from WinOLS's saved
  v0.02.1. A sector is erased and programmed as a unit, so the wrong value
  went to the ECU in the flashed image. Neither the ECU nor the read
  introduced it.
- **WinOLS's saved v0.02.1 has the correct main checksum**
  (`0x00A67C6B`). The error therefore came from the path between that file and
  the ECU: either a different export was flashed, or the flashing tool
  changed the value.

### Reconstructed timeline (owner's recollection plus inference)

The owner recalls that v0.02 stayed on the car until 2018, that the later
versions were written but not flashed, that the cat/O2 edits were what
triggered the trouble, and that the car went on a test drive and home after
the new tune was loaded. It was flashed with the **VAGME7 Flasher** (a
parallel-port "Kick" interface tool). The best fit with the files:

| When | What |
|---|---|
| 2013-10-20 | v0.02 flashed; it stays on the car (recollection) |
| 2016-07-06 | v0.02.1, v0.02.2, v0.03, v0.04 saved, not flashed (recollection; file dates) |
| 2018-05-10 | v0.02.1 flashed **with a bad main checksum** (proven that it reached the ECU; date inferred) → test drive → home → read back as "existing mild tune" (proven read) |
| 2018-05-10, 23:55 | v0.05: correct checksums, **plus the P1681 patch as a precaution**, because the car wasn't nearby and another failure couldn't be risked (recollection; file proven) |
| 2018-05-11 to 14 | v0.06–v0.08 with O2/cat changes; WinOLS didn't re-sign RSA; v0.08 repaired with ME7Sum → `Fixed.bin` flashed (proven: it was still on the ECU on 2026-10-18) |

If v0.02.1 had gone on in 2016 instead, the car would have run for two years
on a bad main checksum, which doesn't fit the no-start behaviour. That's
why May 2018 is the better fit.

### Hypothesis: the flasher's own checksum handling

The VAGME7 Flasher (`VAGME7.exe`, dated 2008, installed 2009-01-07) does
checksum work itself. Its UI text includes "Controlling checksum now…",
"Flash checksum ok/error" and "Cannot find ECU control numbers", and it
accepts scrambled files. A flasher-side "checksum fix" using the wrong
algorithm would explain a self-consistent, wrong main checksum appearing in a
file that WinOLS had saved correctly. **This can't be verified:** the
executable is packed and encrypted (empty code sections on disk, one 609 KB
section at entropy 7.99), so its logic can't be read without unpacking it,
and it left no logs. A different WinOLS export having been flashed remains
the other explanation.

## 4. Why a bad checksum becomes a no-start

**What the ECU stores (third-party, consistent with this repo).** A forum post
on the same failure says the ECU records a checksum error in the EEPROM. It
stores `0x01` at offsets **`0x1C` and `0x2C`** of a 95040 (`0x33` on a
95P08C). The two pages' checksums at `0x1E/1F` and `0x2E/2F` must then be
recalculated. The post's symptom: the ECU runs once, then loses communication
after a restart.

In this repo's terms, those offsets are **page 1 byte 12 and page 2
byte 12**. That's the `dtc_p0601` field in `me7_95040.py`, and the two bytes
95040tool's `clearDTC()` zeroes. About 30 instructions in
`0x8A9Cxx–0x8AA7xx` reference them, including a `cmpb` at `0x8AA712` that
compares the two copies.

**What the ECU acts on at startup (proven from code).** The firmware's
"programming not complete" (P1681) logic is at `0x86C0AE`:

```
86C0AE  c2 f4 f0 be   movbz r4, [0xBEF0]     ; EEPROM shadow byte
86C0B2  66 f4 80 00   and   r4, #0x0080      ; test bit 7
86C0B6  2d 0d         jmpr  cc_Z, +0x0D      ; bit clear -> skip the block
86C0B8  e6 f4 f0 a5   mov   r4, #0xA5F0      ; ...block runs when bit 7 is set
```

`0xBEF0` is in the EEPROM's RAM shadow: record `0x14`, which is **EEPROM
page 30, byte 8**. Page 30 is the programming record, the same page that
carries the flashing tool's stamp. When bit 7 of that byte is set, the ECU
runs the block, which begins by loading the magic value `0xA5F0`. The ECU
then treats itself as not properly programmed.

**Live reads:** the bit was set on this ECU on the morning of 2026-10-18, and was cleared once a programming session completed (section 7).

**Inferred.** The firmware hasn't been traced far enough to show which routine
sets page 30 byte 8 bit 7, or how it relates to the P0601 bytes. Only two
direct code references to that byte exist: the test above and a read at
`0x83B5E8`. The observed sequence is: an image with a bad checksum → an error
stored in EEPROM → refusal to start on a later key cycle. That fits both the
forum report and the original symptom.

## 5. The fix: the P1681 patch (proven)

v0.05 changed **one byte of code**:

```
0x06C0B6 (C166 0x86C0B6):  2d -> 0d     jmpr cc_Z  ->  jmpr cc_UC
```

A conditional branch becomes unconditional, so the "programming not complete"
block **never runs**, whatever the flag says. It is byte-for-byte the same
patch as the community `4Z7907551S-disable-P1681.bin` (software `0020`), at
the same address and with the same surrounding code.

v0.05 also wrote an ASCII marker, `NOREAD` followed by
`00 00 00 00 00 00 03 32`, into erased flash at `0x0FFF90`. Every patched
version carries it, and it stayed on the ECU until it was removed on
2026-10-18 (section 9). What's established about it:

- **It isn't from NefMoto, ME7Sum, ME7EEPROM, me7_95040 or 95040tool.** The
  string appears in none of their sources or binaries (searched as ASCII and
  UTF-16).
- **It isn't part of the community P1681 patch.** `4Z7907551S-disable-P1681.bin`
  has the one-byte patch but no `NOREAD`. So the marker was added by the
  owner's own editing or flashing chain when v0.05 was made.
- **It doesn't block NefMoto.** NefMoto reads this ECU fine, flash included,
  with the marker present.
- **It was written before WinOLS calculated v0.05's checksums, so the
  flasher didn't add it.** `0xFFF90` lies inside multipoint block 66
  (`0xFC000–0xFFFFF`) and the main program checksum range, yet the v0.05 WinOLS
  export passes all 72 checks with the tag present. The VAGME7 Flasher only
  sees the file after it's saved, so it's **ruled out**.
- **It's most likely WinOLS.** A forum report shows WinOLS refusing to open a
  file carrying an ASCII `NOREAD` tag until the tag is blanked. So WinOLS
  honours the marker, and it was present in WinOLS's own export. The exact
  WinOLS feature that wrote it is unconfirmed: the 2005 `WinOLS.exe` on file is
  packed, and its checksum modules don't contain the string.
- In this image the tag is the whole of it: one 16-byte block,
  `NOREAD` + `00 00 00 00 00 00 03 32 00 00`. There's no second hidden byte,
  unlike the forum's file.

### The trade-off

The patch makes the car tolerate any image that fails the check. It also
removes a protection: a genuinely corrupted flash would now run instead of
refusing to. The cleaner state is a correctly signed image, where ME7Sum shows
0 errors, with or without the patch.

## 6. Gap B: RSA after the patch, then repaired with ME7Sum (proven)

From v0.06 on, every additive, background, main and multipoint checksum is
correct. The only failure is the RSA signature:

```
 @a9c28-a9ca8 sig ** NOT OK **
 @16a8a-16b0a mod ** NOT OK **
```

v0.06's signature is **byte-identical** to v0.05's, but v0.06 changed
**29 bytes inside MD5 range 4**. The MD5 changed and the signature didn't, so
the RSA step wasn't re-run on those saves. Because of the patch, the ECU
didn't act on the failure.

On 2018-05-14 the "checksum test" save of v0.08 still failed RSA. The same
day, v0.08 was run through **ME7Sum twice**, producing `Fixed.bin` and
`fudge.bin`. Both have:

- calibration **byte-identical to v0.08**
- **their own random RSA keys** (`9f618324…`, `b62c683b…`), ME7Sum's
  signature
- **0 errors** on all 72 checks, P1681 patch included.

**Until 2026-10-18 the ECU ran `Fixed.bin`, byte for byte.** That day the
flash was read in normal mode with NefMoto (v1.9.8.4, which connects at
`0x11`), with every block verified against the ECU's own checksum. The result
was byte-identical to `Fixed.bin`: v0.08 calibration, ME7Sum key
`9f618324…`, the P1681 patch and the `NOREAD` marker, with 0 ME7Sum errors.
The car had been running the ME7Sum-repaired v0.08 since 2018. The same night
it was reflashed with `NOREAD` removed (section 9).

## 7. The ECU's live state, and the flag clearing (2026-10-18)

The EEPROM was read several times during the day without opening the ECU,
using [`tools/me7_kwp_shadow.py`](../tools/me7_kwp_shadow.py). Reads came from
the RAM shadow and, later, from the chip itself through the ECU's mirror at
`0x600000` (`--mirror`). NefMoto also read page 30 twice. The programming
record on page 30 changed during the session:

| Time | Source | Page 30 bytes 8–10 | Bit 7 ("programming not complete") |
|---|---|---|---|
| 2013 | `bporg95040.bin` | `00 05 0d` | clear |
| 00:44 | RAM shadow | `80 1d 29` | **set** |
| 01:14:18 | NefMoto, page 30 via `0x6001E0` | `80 1d 29` | **set** |
| 01:15:11 | NefMoto enters a **programming session** for a flash read with a **too-small memory layout** selected (*"The ECU may have a larger flash chip than the selected layout (try 29F800)"*). It fails: *"No sector finished, so the programming flag stays set. Use Clear DTCs."* | | |
| 01:15:35–01:20 | NefMoto's second programming-session flash read, with the right layout, **completes every sector** | | |
| ~01:30 | chip mirror | `00 20 2f` | **clear** |
| ~01:40 | RAM shadow | `00 20 2f` | **clear** |

The two reads at ~01:30 and ~01:40 agree on all 25 pages they have in common,
so RAM and chip were in step. The change between 00:44 and 01:30 was the ECU's
state changing, not a difference between sources.

**What this shows (proven).** The bit the P1681 check reads was **set** on
this ECU this morning, and it is **clear now**. At the same time, bytes 9 and
10 rose from `1d 29` to `20 2f`.

**NefMoto calls this flag P0602.** Its bootmode EEPROM tab names bit 7 of
`0x1E8`/`0x1F8` "P0602", and its log calls it "the programming flag". It's the
same bit the P1681 check at `0x86C0B6` reads.

### The rule, tested (02:08–02:16)

A controlled sequence of **reads only** (NefMoto, KWP2000), with page 30 read
through the mirror between steps:

| Step | Page 30 bytes 8–10 | Bit 7 |
|---|---|---|
| Baseline | `00 20 2f` | clear |
| Full Read Flash with a **29F200** layout (warned, continued, completed: first 256 KB) | | |
| Full Read Flash with a **29F400** layout (mirror check failed, continued, completed: first 512 KB) | | |
| ECU reset, page 30 | `80 23 2f` | **set** |
| Full Read Flash with **29F800BB**, 19 sectors (image identical to `Fixed.bin`) | | |
| ECU reset, page 30 | `00 24 35` | **clear** |

**Proven:**

- **A programming-session read with the wrong (too-small) layout sets P0602,
  even when the read completes.** Here, with nothing written, two such reads
  ran without error and the flag was set afterwards.
- **A full read with the correct 29F800BB layout, followed by an ECU reset,
  clears it.** Observed twice: 01:15–01:20 → ~01:30, and 02:13–02:15 → 02:16.

So a stuck P0602 needs **no EEPROM write and no Clear DTCs**: a full read with
the right layout, then a reset, clears it.

**Behaviour after a programming session.** Once a programming session has
been used, the ECU refuses further work until it's reset. `StartDiagnosticSession`
is answered "sub function not supported", requests then fail to send, and
`StopCommunication` returns `ServiceNotSupported`. A fresh connection, starting
with KW1281 at `0x01` and then KWP2000 at `0x11`, works normally again. That's
why page 30 could only be read **after** a reset.

**Not distinguished by these tests:**

- **Whether the reset itself is needed for the clear**, or merely for reading
  it. The flag was never observable between the end of the read and the reset.
- **Coverage or checksum validation.** After each block of a 29F800BB read,
  NefMoto asks the ECU to verify that sector's checksum (19 checks). The
  29F200/29F400 reads made **none**: NefMoto only verifies reads on a
  bottom-boot layout. So "the whole chip was covered" and "the ECU validated the
  whole chip" moved together. **Resolved by NefMoto's documentation:** its
  flashing guide says *"three matching checksums in a row clear"* the bit behind
  P0602, and a completed KWP write ends with exactly that (section 9). So it's
  the ECU's checksum validation that clears the flag.

**When the flag was first set is not known.** It was already set at 00:26,
before tonight's only programming session, and it was clear in the 2013
dump. No log of the event that set it survives; the only older NefMoto log
(2026-10-12) is a launch with no connection. Two candidates fit:

- **A past read attempt with the wrong chip type selected**, the same
  mechanism as above. This matches the owner's recollection.
- **The 2018 flashing** that led to the P1681 patch.

Nothing on file tells them apart. Either way, the P1681 patch was bypassing a
flag that a failed *read* alone can set, not necessarily one left by a bad
flash.

**Bytes 9–10 aren't decoded.** Byte 9 went `1d → 20 → 23 → 24` and byte 10
`29 → 2f → 2f → 35` across the night. Byte 10 rose by exactly **6 for each full
29F800BB read** (twice) and didn't move for the partial reads. That's a pattern,
not a decode.

Over the same period, pages 23–27 (populated at 00:44) returned to all zeros,
pages 7/8 bytes 2–4 returned to their 2013 value `01 54 4f`, and page 17
changed. Nothing in the log shows what reset pages 23–27, so their meaning
stays as given in [95040-format.md](95040-format.md).

Other live values: the P0601 bytes (`0x1C`/`0x2C`) are `00`, and the
immobiliser flag is `02 02`, off (see [immo-off.md](immo-off.md)).

**Consequences:**

- With the flag clear, an unpatched image would no longer trip the P1681 check
  *on this flag's account*. The patch still protects against the next
  **interrupted** programming session, which would set the flag again. Keep it
  unless there's a reason to remove it, and if you do remove it, read page 30
  first (`me7_kwp_shadow.py --mirror`) and make sure bit 7 is clear.
- Writing pages 30/31 directly to clear the flag is **not needed**, and was
  never tried. A full correct-layout read and a reset did it.
- **Select the right memory layout (29F800BB for this ECU) before any flash
  read or write.** Any programming-session read with a wrong layout sets the
  flag, even one that completes. If that happens: do a full 29F800BB read, reset
  the ECU, then confirm page 30 with `me7_kwp_shadow.py --mirror` or NefMoto's
  **Read EEPROM Mirror**.

## 8. Recovery options, from cleanest to bluntest

1. **Re-sign the image before flashing.** `me7sum in.bin out.bin` replaces
   the modulus and signature with a fresh key pair and fixes every other
   checksum. Then check: `me7sum out.bin` must report 0 errors. Run that check
   before every flash, whatever tool made the edit, and ideally check a
   readout after flashing too. Gap A was a bad checksum on the car, not in the
   saved file.
2. **Clear the stored error in the EEPROM**, if one was set. Zero `0x1C` and
   `0x2C`, then recompute **both** page checksums. Pages 1 and 2 are separate
   records, each checksummed with its own index, so page 2's checksum must be
   recomputed, **not copied** from page 1. On this ECU's EEPROM:

   ```
   clear    0x1C=00  0x1E/1F = 31 fc     0x2C=00  0x2E/2F = 30 fc
   flagged  0x1C=01  0x1E/1F = 30 fc     0x2C=01  0x2E/2F = 2f fc
   ```

   `me7_95040.py` validates the result, and `-f` shows the `dtc_p0601` field.
3. **Patch out the P1681 check** (what was done here). It works and survives
   later bad checksums, with the trade-off above.

A bricked ECU that no longer talks over OBD is recovered in **bootmode**,
which runs from the C167 mask ROM whatever the flash contains.

## 9. Removing NOREAD (2026-10-18)

The `NOREAD` tag was removed and the result flashed, keeping everything else
as it was, P1681 patch included.

**How the image was made:**

1. Start from the ECU's own read (`== Fixed.bin`).
2. Set the 16-byte block at `0xFFF90` to `FF`.
3. Run ME7Sum. Exactly the two checksums covering that area failed, and it fixed
   them: the **main program checksum** (`@0xFFFE0`) and **multipoint block 66**
   (`0xFC000–0xFFFFF`). The re-check showed 0 errors on all 72 checks.

The result differs from the previous flash in **28 bytes in three places**: the
multipoint table entry for block 66 (`0x1FFF6`, 7 bytes), the tag (16 bytes)
and the program checksum (`0xFFFE0`, 7 bytes). The calibration, the RSA
modulus and signature, and the P1681 byte are unchanged. The last 16 KB block
is now byte-identical to stock's, and its checksum is back to stock's
`1FFDE002`. Final image sha256: `cc11e501b0f160ee…`.

**How it was flashed.** With NefMoto v1.9.8.4 over KWP2000 (HEX-USB+CAN,
29F800BB layout, Verify Write on), after a full pre-write read that matched
`Fixed.bin`:

- **Full Write:** 19 of 19 sectors erased, programmed and checksum-verified by
  the ECU.
- One transient `BlockTransferDataChecksumError` on a routine-result poll
  mid-write. NefMoto carried on, and every sector then verified.
- At the end, NefMoto logged *"Sent 3 matching checksums with the upload
  closed. The programming flag should be clear."* Its flashing guide documents
  the mechanism: three matching checksums in a row clear the bit behind P0602.

**Verified afterwards:**

| Check | Result |
|---|---|
| Read-back vs flashed image | byte-identical (`cc11e501…`) |
| ME7Sum on the read-back | 0 errors |
| `NOREAD` anywhere in flash | none |
| P1681 patch (`0x6C0B6`) | still `0d` |
| Page 30 after an ECU reset | `00 28 42`, bit 7 **clear** |

As with any flash, the ECU's learned adaptations reset. Never flash a copy with
the tag stripped and the checksums *not* recalculated: the tag lies inside
checksummed flash.

## Reproducing

Build ME7Sum from source on Windows (VS 2022 with the C++ workload). Its own
`build.cmd` has LF line endings, which `cmd` mishandles, so call the compiler
directly:

```bat
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
cl /nologo /EHsc /O2 /Feme7sum.exe -D__GIT_VERSION=\"local\" /Tc crc32.c inifile_prop.c me7sum.c utils.c str.c range.c inifile\inifile.c os\pgetopt.c rsa.c md5.c Ws2_32.lib mpir\mpir-2017.lib
```

With only an input file, `me7sum image.bin` checks and reports without
writing anything. These identify which tool signed an image and whether it is
patched:

```python
d = open("image.bin", "rb").read()
print({0x2D: "stock", 0x0D: "P1681 patched"}.get(d[0x6C0B6], "unknown"))
print({"a7f24715": "stock key", "05915e15": "WinOLS fixed key"}.get(
    d[0x16A8A:0x16A8E].hex(), "other key (ME7Sum generates a new one per run)"))
```

To recover versions from a WinOLS project (this WinOLS version stores them
raw), find each ME7 ident and take the 1 MB around it:

```python
import re
d = open("project.ols", "rb").read()
for n, m in enumerate(re.finditer(rb"ME7\.1\.1/5/6030", d)):
    start = m.start() - 0x01000A          # ident text sits at image 0x01000A
    open(f"version{n}.bin", "wb").write(d[start:start + 0x100000])
```

Addresses apply to software `1037367582` (and `0020` for the P1681 site).
Other builds will differ.
