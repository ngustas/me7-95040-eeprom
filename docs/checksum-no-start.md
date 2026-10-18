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
- The WinOLS export of v0.02.1 is correct. So the bad value came from
  whatever wrote the image to the car, not from the saved file. *Which tool
  that was is unknown.*

**Inferred:** this is the "incomplete checksum calculation" the car was
carrying when the trouble showed. The readout and the v0.05 "fix for
programming not complete error" are from the same day.

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

**Live read: the bit is set on this ECU today** (section 7).

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
version carries it. Its purpose is **not known**.

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

Which image was flashed last is **unknown**. The live EEPROM read below can't
answer that, because it reads the EEPROM, not the flash. A flash read would:
current NefMoto connects to this ECU, since it retries slow init at `0x11`.

## 7. The ECU's live state (2026-10-18)

The EEPROM contents were read from the running ECU's RAM shadow over KWP2000
with [`tools/me7_kwp_shadow.py`](../tools/me7_kwp_shadow.py), without opening
the ECU. The rebuilt page image validates cleanly. Compared with the 2013
dump:

| What | 2013 dump | Live (2026) |
|---|---|---|
| P0601 bytes, `0x1C` / `0x2C` | `00` / `00` | `00` / `00` (clear) |
| **Page 30 byte 8** ("programming not complete") | `00` | **`80`: bit 7 set** |
| Page 30 bytes 9–10 | `05 0d` | `1d 29` |
| Immobiliser flag, `0x12` / `0x22` | `01` / `01` | `02` / `02` (off; see [immo-off.md](immo-off.md)) |

This **proves** the flag that the P1681 check reads is **set on this ECU right
now**. Unpatched firmware would run the "programming not complete" block. The
P1681 patch is what keeps the car running, not a clean flag. Two consequences:

- **Don't flash an unpatched image** (for example stock, v0.01–v0.04 or
  v0.02.x) onto this ECU without dealing with that flag first. The ECU would act
  on it.
- Clearing it would mean writing pages 30/31, which are a mirrored pair
  (page 31 borrows page 30's checksum index). **This hasn't been tried.** Nothing
  here shows that bit 7 is the only thing that matters, and bytes 9–10 changed
  too.

Which routine set the flag, and when, still isn't known (see section 4). The
P0601 bytes are clear, so if that path stored an error, it has been cleared
since.

Pages 5–7, 17 and 23–27 also changed. Pages 23–27 went from all zeros to
repeating 6-byte entries. What those pages hold is covered, or flagged as
unknown, in [95040-format.md](95040-format.md). They play no known part in
this story.

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
