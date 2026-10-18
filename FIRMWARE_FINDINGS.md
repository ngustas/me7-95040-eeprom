# ME7.1.1 95040 page map, taken from the firmware

What this covers: firmware `4Z7907551S` / 0261208288 / 1037367582, file
`original bins/bporg-551S.bin` (MD5 `69fc0ae37d0e6b7f94cb19180c24c9bc`).
Note that this is **not** the `4Z7907551S.bin` in nyetwurk's ME7Sum set
(`f298f584...`). The addresses below apply to this image only. Other builds
will move them, but the structures should be the same.

Tooling: Ghidra 12.1.2, keyhana/c166-ghidra-module v1.2.2
(`C166:LE:16:default`, cspec `tasking`), and nyetwurk/ghidra-me7-analyzer
v0.0.2 `ME7SetupScript` as the pre-script. Flash is at 0x800000. DPP0-3 are
0x0204/0x0205/0x00E0/0x0003. Ghidra's C167 support worked well for this job.
The disassembly is clean and the decompiler is usable. The scripts I used are
in `ghidra_scripts/`.

All "16-bit" RAM addresses below go through DPP2 (0x00E0), so `0xBDA8` is the
physical address `0x383DA8`.

---

## 1. The driver stack (high confidence)

| Layer | Address | What it does |
|---|---|---|
| SSC init | `0x8231D8` | Sets `SSCCON=r12`, `SSCBR=r13`. The application calls it as `(0x4637, 0x000F, 2)`. |
| SSC byte xfer | `0x8231EE` | Writes `SSCTB`, waits on `SSCCON.12`, reads `SSCRB`. |
| SSC block rx / tx | `0x82328C` / `0x82322E` | Bulk receive / send to a far pointer. |
| `eep_rdsr(dst)` | `0x8AD684` | `CS=P6.3` low, sends `0x05` (RDSR) and reads the status byte. |
| `eep_cmd(op)` | `0x8AD932` | Sends one opcode byte. Used as `0x06` = WREN. |
| `eep_wrsr(v)` | `0x8AD754` | WREN, then `0x01` (WRSR). Saves `v & 0x0C` (BP1:BP0) to `0xA813`. |
| **`eep_read(len, ee_addr, dst)`** | `0x8AD822` | Checks RDSR against the expected BP bits, then reads. |
| **`eep_write(len, ee_addr, src)`** | `0x8AD97A` | WREN, then write. Increments a write counter at `0xBD86` (`sub 0xbd86,ONES`). |
| error report | `0x8AD678` | Codes 0x81 = RDSR, 0x83 = read, 0x84 = write, 0x85 = cmd, 0x86 = bad field. |

Both `eep_read` and `eep_write` have two addressing paths, picked by
**`0xFDB4` bit 2**:

* bit clear: **M95040 9-bit form**, `cmd = 0x03 | (A8<<3)` (read) or
  `0x02 | (A8<<3)` (write), followed by one address byte.
* bit set: 16-bit form, `cmd 0x03` / `0x02` followed by two address bytes,
  i.e. a 95080/95160/95320-class part.

This bears directly on PR #136. The firmware supports both address widths and
selects one with a RAM flag.

The flash kernel carries its own copy of the same driver (`P6.3`, SSC). It runs
from `0x3864D0..0x386E50`, which is flash `0x80C2B6..` plus the kernel offset of
0x5DE6.

## 2. The page attribute table: firmware confirmation of the checksum model

`0x816E00` holds 32 words, one per page: `word = (record_id << 8) | flags`.
Every page access goes through this table: `0x8ADDCE`, `0x8AE0D2`, `0x8AE89C`
and `0x8AEF44` all read `[0x816E00 + page*2]`.

| flag bit | meaning | how it was established |
|---|---|---|
| 0 (0x01) | page carries a checksum (14-byte payload; checksum at +14) | `0x8AE89C` uses 14 vs 16 bytes; `0x8ADDCE` updates the checksum only when this bit is set |
| 1 (0x02) | page is shadowed in RAM and kept in sync by the background task | `0x8AEF44` skips pages where it is clear; `0x8ADDCE` rejects writes (err 0x86) |
| 6 (0x40) | second copy of a pair: checksum index is `page-1` | `0x8AE89C`: `page -= (flags & 0x40) >> 6` |
| 7 (0x80) | member of a mirrored pair | `0x8AE89C` |
| 2, 4, 5 | **not identified** | |

Decoded for this image:

* bit 0 is clear on pages **0, 17, 18, 19**. That is exactly `NO_CHECKSUM_PAGES`.
* bit 6 is set on pages **8, 10, 12, 14, 16, 31**. That is exactly `BACKUP_PAGES`.

So both lists the tool took from 95040tool are now confirmed from ECU code.

`0x8ADDCE` updates the checksum incrementally as
`ck += (old_lo-new_lo) + (old_hi-new_hi)`. That keeps
`ck = K - sum(payload)`, which matches the formula in `me7_95040.py`.

### Record ids and the RAM shadow

The shadow base is the word at `0x816FA8`, which is `0xBDA8`.
Record `id` occupies `0xBDA8 + id*16`. The per-page status bytes live at
`0xBD88 + page` (bit 0x10 = read failed, 0x20 = write failed, 0x40 = compare
failed). The write counter is at `0xBD86`.

| record | pages | shadow | swept (bit1) |
|---|---|---|---|
| 0x00..0x05 | 1, 2, 3, 4, 5, 6 (one each) | 0xBDA8..0xBE07 | yes |
| 0x06 | 7 + 8 | 0xBE08 | both |
| 0x07 | 9 + 10 | 0xBE18 | both |
| 0x08 | 11 + 12 | 0xBE28 | both |
| 0x09 | 13 + 14 | 0xBE38 | both |
| 0x0A | 15 + 16 | 0xBE48 | both |
| 0x0B | 17, 18, 19 | 0xBE58 | **17 only** |
| 0x0C..0x12 | 20..26 (one each) | 0xBE68..0xBED7 | yes |
| 0x13 | 27, 28, 29 | 0xBED8 | **27 only** |
| 0x14 | 30 + 31 | 0xBEE8 | both |
| 0xFF | 0 | none | no |

**Why mirrored pairs are byte-identical:** both pages of a pair are swept
against the same 16-byte shadow slot. `0x8AE0D2` reads the page, compares it to
the slot (`0x8ADCE6`) and writes the slot back if they differ. The ECU therefore
always stores the pair from a single RAM copy, so a pair's two pages share one
payload and carry the first page's checksum.

Pages 1/2 and 3/4 are a different case. They are separate records (ids 0/1 and
2/3) that the application writes twice. See `0x8AA476` below.

Page 0 (signature) is outside the table. The application reads and writes it
directly as 1 byte at EEPROM address `0x00F` (byte 15, the `0x5A`):
read at `0x8A4246`/`0x8A42BA`, written at `0x8A4290`.

### Field writers

* `0x8ADDCE(value16, page, offset)` writes a word.
* `0x8ADD0A(value8, page, offset)` writes a byte.

The compiler emits the offset as `mov r14,#&field ; sub r14,#0xBDA8 ; and r14,#0xF`.
So the immediate gives the exact field address, and `r13` is the literal page.
I enumerated all 22 + 43 call sites. The decompiled consumers below come from
those sites plus every direct reference into `0xBDA8..0xBEF7`.

## 3. Alignment check against the already-named fields (passes)

| known field | firmware evidence |
|---|---|
| immo flag 1[2] / 2[2] | `0x88387A` and `0x8A5A82` touch shadow 1[2] and 2[2]. `0x8A5A82` writes page 1 through `0x8ADD0A`. |
| SKC 3[2:4], cluster code 3[4:10] | `0x884952` reads 3[2], 3[4] and 3[5]. |
| VIN 11[5:10] + 13[0:12] | `0x885040` reads 11[5], 11[6] and 13[1]. |
| immo ID 13[12] + 15[0:13] | `0x885090` reads **13[12]** and 15[1], which is exactly where the field starts. |
| page 1 read | `0x88353E`: `eep_read(16, 0x010, sp)`, a direct read of page 1. |

All of these sit together in `0x8838xx..0x8855xx` (the immobiliser block), and
the offsets match the existing table. The page numbering is aligned.

## 4. New identifications

### Pages 5 and 6: learned values with flash defaults (high confidence on structure; module name unknown)

**This corrects the earlier conclusion that these pages are "factory-written
calibration, not learned adaptation".** They are runtime-learned values. A
virgin chip already holds them because the firmware seeds them from flash
defaults.

* Owner: one module at `0x862F00..0x8644FF`.
* Restore at init (`0x862F52..0x862FD2`): skipped if page-status `0xBD8D` (page
  5) or `0xBD8E` (page 6) has bits 0x98 set. Otherwise it copies shadow to RAM:

| EEPROM | RAM | flash default (`0x86305E`) | default | bp / virgin / awu / 2392 |
|---|---|---|---|---|
| 5[2:4] | `0xBD04` | `0x8137FC` | 0x0268 | 0x0264 0x0273 0x0284 0x0259 |
| 5[4:6] | `0xBD08` | `0x813804` | 0x0278 | 0x01E1 0x01C6 0x01A8 0x01AD |
| 5[6:8] | `0xBD0A` | constant 0 | 0x0000 | 0xFFFB 0xFFFB 0x0000 0x0001 |
| 5[8:10] | `0xBD0C` | `0x813808` | 0x0429 | 0x0436 0x0436 0x042B 0x0423 |
| 5[10:12] | `0xBD12` | `0x81382C` | 0x217B | 0x0AED 0x0E06 0x1259 0x0E58 |
| 5[12:14] | flags | - | - | bit0 -> `0xB37D.0`, bit2 -> `0xB37D.1` |
| 6[2:4] | `0xBD06` | `0x8137FE` | 0x0D99 | 0x0D97 0x0D86 0x0D7B 0x0DA0 |
| 6[4:6] | `0xBD0E` | `0x81381A` | 0x0D66 | 0x0E14 0x0E38 0x0E56 0x0E4E |

* `0x86305E` loads the defaults and clears flags `0xB37D` bits 0-1.
* `0x8637B2` and `0x86391C` write the values back through `0x8ADDCE`. Their
  enable gates compare runtime values `0x3806D9`/`0x3806DB` against flash
  limits `0x810BC5..0x810BC9`, and they raise this module's own fault indices
  (`0x380633` = 5..9, 0x18, 0x19, 0x1B, 0x1C, 0x1E).
* 5[6:8] has a default of exactly 0 and holds small signed values (-5, -5, 0, +1).
  That is the shape of an offset adaptation.
* The defaults for 5[2], 5[8] and 6[2] sit in the middle of the four images'
  values, while 5[4], 5[10] and 6[4] have drifted away from theirs. Both
  patterns fit learned values and do not fit fixed constants.
* **Not identified:** which ME7 function this module is (e.g. throttle/EGAS,
  fuel-trim or idle adaptation). Without DAMOS labels I am not naming it.

**Page 6 bytes 8-11:** these belong to a different routine, `0x8627E4`.
6[8:10] is a word from RAM `0xBD02`, written only when `0xFD00.9` or `0xFD08.8`
is set. 6[10] is a byte from RAM `0xB37C`. `0x8C3D6E` compares and rewrites
page 6 as well. Meaning not identified.

### Pages 7 and 8: one record (id 0x06), flag byte at offset 7 (structure high confidence; meaning unknown)

* 7[7] is a bitfield of latches. `0x88B5BA` sets and clears bits 0, 1, 2, 3
  and 4 on it individually through `0x8ADD0A`, at 10 call sites. It is also
  read by `0x89BC02`, `0x89BC9A`, `0x83AF2A`, `0x88B122`, `0x88A350`, and
  `0x88C46C..0x88C4E6`.
* `0x88B122` reads 7[2], 7[3], 7[4] and 7[10:12]. `0x88A350` reads 7[5], 7[6]
  and 7[8:10]. `0x89BF08` uses 7[2] and 7[15] (the checksum high byte, as part
  of a slot copy).
* The owners are in `0x88A3xx..0x88C5xx` and `0x89BCxx..0x89C1xx`, just after
  the immobiliser block. Meaning not identified.

### Pages 9 and 10: not constant (correction)

They are identical across all four dumps, but the firmware **does write them**.
`0x88C468` writes 9[12] through `0x8ADD0A`, and `0x89BF08` writes page 9 and
reads 9[0], 9[1] by index. `0x84EFC4` reads 9[8] by index. Most bytes are 0x80,
which reads as a neutral default for signed-byte values. A different 9/10 on an
adapted ECU should be treated as plausible, not as a bad read. I softened the
canary message in the tool to say so.

### Page 17 (with 18, 19): immobiliser-area counters (medium confidence)

* `0x883F1C` and `0x8854A6`/`0x885504` (immobiliser block) write 17[6] and
  17[7] through `0x8ADD0A`. They also queue a direct EEPROM job:
  `0x382100 = {page 0x11, offset, len 1, op 5}` -> `0x8AE3F6(0xA100)`.
* The value saturates at 0x7F and is OR'd with 0x80. It behaves like a
  per-channel attempt counter with a "set" bit.
* 17[2:4] and 17[4:6] are read at `0x883644`/`0x883648`.
* **Pages 18 and 19** carry no checksum and are not swept (flags 0x10). I found
  **no application access** to them. They are reachable only through the
  diagnostic job engine (`0x8AE89C`). The populated 19 in 2392.bin was probably
  written by a tester. Meaning not identified.

### Pages 21, 22, 24: one module, `0x84B5xx..0x84C3xx` (structure only)

* 21[8..13] and 22[0..4] form one logical byte array. `0x84BF4E` reads them in
  order and skips 21[14:16], which is 21's checksum. `0x84C074` writes 21[8],
  21[10], 21[12], 22[0], 22[2] and 22[4], plus a byte to page 22 through
  `0x8ADD0A`. The array crossing the page boundary while skipping the checksum
  is good evidence that the two pages hold one field.
* 24[0] and 24[1] are bytes from RAM `0x384005` / `0x384004`, written by
  `0x84B5D2` when they change.
* Meaning not identified.

### Pages 22, 25, 26, 27 (the "always zero" pages)

* **22** is used (see above). It is only zero in the dumps.
* **25** is written: `0x8C1EAA` writes 0 and `0x8C22B6` writes a byte, both
  through `0x8ADD0A`. `0x8A6A4C` reads 25[7]. Meaning not identified.
* **26**: no application reference found.
* **27** is the head of record 0x13 (27/28/29: zeros / part number / variant).
  Only 27 is swept; 28 and 29 are not swept (factory or tester-written ID data).
  No application reference to the record's bytes was found.

These pages are not reserved padding. `ALWAYS_ZERO` in the tool remains an
observation, not a rule.

### Page 23: not identified

Record 0x0F. It has a checksum and is swept, but no direct or indexed reference
showed up. bp.bin and 2392.bin hold data there, so something does write it.
The likeliest path is the generic job engine or an indexed access the constant
propagator did not resolve.

### Pages 1/2 bytes 10-12 (bonus, medium confidence)

`0x8AA476` writes **the same constant pair to 1[10:12] and 2[10:12]**:
`69 C1`, `8E` / `5A`, or `33`. `0x8AA70E` writes 0 to 1[12] and 2[12], and
`0x8A9CBA` writes 0xFF to both pages. bp, awu and 2392 hold `69 C1`; virgin
holds `5A 8E`. This is a state code the immobiliser logic sets by assignment.
I have not worked out which code means which state.

---

## Could not identify

* Meaning of pages **5, 6** (the module is pinned down; its ME7 function name is not).
* Meaning of **page 6 bytes 8-11**.
* Meaning of pages **7/8** (only the layout is known).
* Meaning of pages **9/10** (shown to be written at runtime; not named).
* Meaning of pages **18, 19, 23, 26** (no application access found).
* Meaning of pages **21, 22, 24, 25** (owner and layout known; not named).
* Attribute-table flag bits **2, 4 and 5**.

## What went into `me7_95040.py`

* Comments recording firmware confirmation of `NO_CHECKSUM_PAGES` and `BACKUP_PAGES`.
* `PAGE_RECORD`: the page -> record-id map from `0x816E00`, with a note that it
  is for this build.
* Two hex-only fields named after what the code proves, not what it might mean:
  `adapt_p5p6` (the learned words on pages 5/6) and `flags_p7` (the latched
  bitfield at 7[7]).
* A softer canary message for page 9.

No semantic names were added for the unidentified pages.
