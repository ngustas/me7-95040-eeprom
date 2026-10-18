# The checksum no-start: what happened and how it was fixed

The reference ECU (`4Z7907551S`, software `1037367582`) went through a
classic ME7 failure. A tune saved with an incomplete checksum calculation
started normally, then **refused to start after a couple of key cycles**. It
was fixed by patching the flash. This document reconstructs the whole chain
from the saved tune versions, ME7Sum, the firmware and the EEPROM format.

What is **proven** below is marked as such. What is **inferred** is marked
too. The images that actually caused the no-start were not kept, so part of
the story is necessarily reconstructed.

## 1. ME7 checks its own flash in many ways

ME7Sum (nyetwurk) finds **72 separate checks** in this firmware. All of them
must pass:

| Check | What it covers |
|---|---|
| ROMSYS additive sums | Startup section, all-param page, program pages |
| CRC tables | Fixed tables in the image |
| **RSA signature** | An MD5 over four calibration ranges (`0x10002–0x13FFE`, `0x14382–0x17F4E`, `0x18192–0x1FBDC`, `0x26A00–0x2FFFC`), signed with RSA (exponent 3). Signature at `0xA9C28`, modulus at `0x16A8A` |
| Main data checksum | The same four calibration ranges, as a 32-bit sum |
| Background checksums | Code ranges re-summed while the engine runs |
| Main program checksum | `0x020000–0x0FFFFF` |
| Multipoint checksums | 66 blocks of 16 KB across the whole image |

A tuning tool has to correct **every** one of these after a map edit. The
additive ones are easy. RSA can't be re-signed with Bosch's key. Tools get
around this by putting a **new modulus** in the image, from a key pair whose
private half they hold, and signing the new MD5 with it. The ECU reads the
modulus from the image, so it accepts the substitute.

## 2. Checking every saved version (proven)

ME7Sum was built from source with MSVC (see [Reproducing](#reproducing)) and
run against each saved version of the tune:

| Version | Saved | ME7Sum result | Code patch |
|---|---|---|---|
| Original (stock) | 2013-10-20 | **0 errors** | — |
| v0.01 load bump | 2013-10-20 | **0 errors** | — |
| v0.02 mild tune | 2013-10-20 | **0 errors** | — |
| *v0.03, v0.04* | *not kept* | *—* | *—* |
| v0.05 HOT tune, "fix for programming not complete error" | 2018-05-10 | **0 errors** | **P1681 patch** |
| v0.06 HOT tune (×2 variants) | 2018-05-11 | **1 error: RSA** | P1681 patch |
| v0.07 secondary air disabled | 2018-05-11 | **1 error: RSA** | P1681 patch |
| v0.08 cat efficiency window | 2018-05-11/13 | **1 error: RSA** | P1681 patch |
| "test or recreation of v0.08, checksum test" | 2018-05-14 | **1 error: RSA** (byte-identical to v0.08) | P1681 patch |

From v0.06 on, **every additive, background, main and multipoint checksum is
correct**. The only failure is the RSA signature:

```
 @a9c28-a9ca8 sig ** NOT OK **
 @16a8a-16b0a mod ** NOT OK **
```

### Why RSA broke at v0.06 (proven)

- v0.06's signature is **byte-identical** to v0.05's.
- v0.06 changed **29 bytes inside MD5 range 4** relative to v0.05.

So the MD5 changed but the signature didn't: the RSA step was simply not
re-run when v0.06 was saved. The tool fixed every sum it knew about and
skipped the one that needs a signing key. That is the "incomplete checksum
calculation".

### Which tool signed the good versions (proven by elimination)

Every modified version, from 2013 and 2018 alike, carries the **same
replacement modulus**. ME7Sum generates a fresh random key on every run
(`srand(time(NULL))` in `rsa.c`), so it would never produce the same modulus
twice. The good versions were therefore signed by a **fixed-key** tool. That
is consistent with WinOLS's checksum module. The modulus is not in ME7Sum's
source.

## 3. Why a bad checksum becomes a no-start

**What the ECU stores (third-party, consistent with this repo's format).** A
forum post on the same failure reports that the ECU records the checksum error
in the EEPROM. It stores `0x01` at offsets **`0x1C` and `0x2C`** of a 95040
(`0x33` on a 95P08C), and the two pages' checksums at `0x1E/1F` and `0x2E/2F`
must then be recalculated. The post describes the symptom: the ECU runs the
first time, then loses communication after a restart.

In this repo's terms, those offsets are **page 1 byte 12 and page 2 byte 12**.
That is the `dtc_p0601` field in `me7_95040.py`, and exactly the two bytes
95040tool's `clearDTC()` zeroes (28 and 44 decimal). The firmware handles them
heavily: about 30 instructions in `0x8A9Cxx–0x8AA7xx` reference them,
including a `cmpb` at `0x8AA712` that compares the two copies.

**What the ECU acts on at startup (proven from code).** The firmware's
"programming not complete" (P1681) logic is at `0x86C0AE`:

```
86C0AE  c2 f4 f0 be   movbz r4, [0xBEF0]     ; EEPROM shadow byte
86C0B2  66 f4 80 00   and   r4, #0x0080      ; test bit 7
86C0B6  2d 0d         jmpr  cc_Z, +0x0D      ; bit clear -> skip the block
86C0B8  e6 f4 f0 a5   mov   r4, #0xA5F0      ; ...block runs when bit 7 is set
```

`0xBEF0` is in the EEPROM's RAM shadow: record `0x14`, which is **EEPROM page
30, byte 8**. Page 30 is the programming record, the same page that carries
the flashing tool's stamp. When bit 7 of that byte is set, the ECU runs the
block, which starts by loading the magic value `0xA5F0`. The ECU then treats
itself as not properly programmed.

**Inferred.** The firmware hasn't been traced far enough here to show which
routine sets page 30 byte 8 bit 7, or exactly how it relates to the P0601
bytes. Only two direct code references to that byte exist: the test above and
a read at `0x83B5E8`. The likely writer is the generic page writer or the
flash loader itself. The observed behaviour is: an image with a bad checksum
→ an error stored in EEPROM → refusal to start on a later key cycle. That fits
both the forum report and the original symptom.

## 4. The fix that was applied: the P1681 patch (proven)

v0.05 changed **one byte of code**:

```
0x06C0B6 (C166 0x86C0B6):  2d -> 0d     jmpr cc_Z  ->  jmpr cc_UC
```

A conditional branch becomes unconditional, so the "programming not complete"
block **never runs**, whatever the flag says.

This is byte-for-byte the same patch as the community
`4Z7907551S-disable-P1681.bin` (software `0020`). The code is identical at
the same address in both software levels.

That is why the car **ran for years on v0.06–v0.08** even though their RSA
signature is wrong: the patch stops the ECU acting on the failure.

v0.05 also wrote an ASCII marker, `NOREAD` followed by `00 00 00 00 00 00 03
32`, into erased flash at `0x0FFF90`. Its purpose is **not known**. It may
come from whatever tool applied the patch.

### The trade-off

The patch makes the car tolerate *any* image that fails the check, which is
exactly why it worked. It also removes a protection: a genuinely corrupted
flash would now run instead of refusing to. The cleaner long-term state is a
**correctly signed image** (ME7Sum shows 0 errors) *plus* the patch, or a
correctly signed image on its own.

## 5. Recovery options, from cleanest to bluntest

1. **Re-sign the image before flashing.** `me7sum in.bin out.bin` replaces
   the modulus and signature with a fresh key pair and fixes every other
   checksum. Then check: `me7sum out.bin` must report 0 errors. Always run that
   check before flashing, whatever tool did the edit.
2. **Clear the stored error in the EEPROM**, if one was set. Zero `0x1C` and
   `0x2C`, then recompute **both** page checksums. Pages 1 and 2 are
   *separate records*, each checksummed with its own index, so page 2's
   checksum must be recomputed, **not copied** from page 1. On this ECU's
   EEPROM:

   ```
   clear    0x1C=00  0x1E/1F = 31 fc     0x2C=00  0x2E/2F = 30 fc
   flagged  0x1C=01  0x1E/1F = 30 fc     0x2C=01  0x2E/2F = 2f fc
   ```

   `me7_95040.py` validates the result, and `-f` shows the `dtc_p0601` field.
3. **Patch out the P1681 check** (the fix used here). It works and survives
   later bad checksums, with the trade-off above.

A bricked ECU that no longer talks over OBD is recovered in **bootmode**,
which runs from the C167 mask ROM whatever the flash contains. Write a good
flash image, and fix the EEPROM if needed.

## Reproducing

Build ME7Sum from source on Windows (VS 2022 with the C++ workload). Its own
`build.cmd` has LF line endings, which `cmd` mishandles, so call the compiler
directly:

```bat
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
cl /nologo /EHsc /O2 /Feme7sum.exe -D__GIT_VERSION=\"local\" /Tc crc32.c inifile_prop.c me7sum.c utils.c str.c range.c inifile\inifile.c os\pgetopt.c rsa.c md5.c Ws2_32.lib mpir\mpir-2017.lib
```

With only an input file, `me7sum image.bin` checks and reports without
writing anything. Check for the P1681 patch:

```python
d = open("image.bin", "rb").read()
print({0x2D: "stock", 0x0D: "P1681 patched"}.get(d[0x6C0B6], "unknown"))
```

Addresses apply to software `1037367582` (and `0020` for the P1681 site).
Other builds will differ.
