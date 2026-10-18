# Prior-art ME7 EEPROM tools

Three older community tools were examined. **None of the executables was run.**
Everything here comes from static inspection: archive contents, embedded
strings, and recovered Python bytecode.

## 95040tool 0.1 (`95040tool-0.1.zip`, files.s4wiki.com)

It describes itself as "View/Modify me7.5 eeprom files". It is a **py2exe**
app, so its Python source survives as bytecode: unzip the archive, unzip the
`library.zip` inside it, then read `__main__95040tool__.pyc`:

```bash
python tools/pyc27.py tree __main__95040tool__.pyc
python tools/pyc27.py dis  __main__95040tool__.pyc validateChecksum
```

What it gives:

- **Page lists**, as class constants:
  `noCheckSumPages = [0, 17, 18, 19]` and `backupPage = [8, 10, 12, 14, 16, 31]`.
- **Checksum** (`validateChecksum`):

  ```python
  minus = 2 if pageno in backupPage else 1
  bytesum = sum(data[pageno][0:14])
  calcsum = 65535 - (pageno - minus) - bytesum
  ```

- **Field offsets** (`parse`, `setVIN`, `clearDTC`), as `data[page][byte]`:

  | Field | Location |
  |---|---|
  | SKC | `'%02x%02x' % (data[3][3], data[3][2])` as decimal, zero-padded |
  | Cluster code | `data[3][4:10]` |
  | Immobiliser | `data[1][2] == data[2][2] == 1` means on |
  | P0601 DTC | `data[1][12]`, `data[2][12]` (`clearDTC` zeroes bytes 28 and 44) |
  | VIN | `data[11][5:10] + data[13][0:12]` |

- **Features**: status display, immobiliser on/off, set VIN, clear P0601, and
  fix checksums including resyncing the backup pages. The VIN detail decode
  uses built-in WMI, model-year and plant tables.

All of this agrees with the four dumps and with the ECU firmware.

## ME7EEPROM 1.40 (`me7-eeprom-1.40.zip`)

A native command-line tool, *"Allows to program ME7 ECU's EEPROM"*. It needs
a dumb serial-to-K-line cable. It does no field decoding: `--screen` is a hex
dump. It is useful as **prior art for multi-chip bootmode support**:

```
--bootmode MEM_TYPE   Allowed memory types: [95040 | 95080 | 95160 | 95P08]
--CSpin               Set the CPU chip select (CS) output. eg: P4.7
```

It embeds the C167 port register table used for chip select:

| Port | PortReg | DirControlReg |
|---|---|---|
| P2 | `0xFFC0` | `0xFFC2` |
| P3 | `0xFFC4` | `0xFFC6` |
| P4 | `0xFFC8` | `0xFFCA` |
| P6 | `0xFFCC` | `0xFFCE` |
| P7 | `0xFFD0` | `0xFFD2` |
| P8 | `0xFFD4` | `0xFFD6` |

P5 is absent, which is correct: it is input-only on the C167. ME7.1.1 uses
**P6.3**, so `0xFFCC` / `0xFFCE` bit 3.

Other details: baud rates 9600, 10400 (default), 19200 and 57600. It can read
over OBD (read only) and read or write in bootmode. It checks the C167
identification response and rejects the 8xC166 and early C165/C167 parts.

**Gap worth noting:** `95P08` is in this tool's list but not in NefMoto
PR #136's device catalog.

## me7_95040 1.31 (`me7_95040_v1.31.zip`)

The older ancestor of ME7EEPROM: 95040 only, with no `--CSpin`. It has the
same OBD and bootmode modes. The two copies found (top-level and `legacy/`)
are byte-identical.
