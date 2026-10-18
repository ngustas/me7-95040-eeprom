# Remote bench access for an ME7 ECU

This describes how to give a remote developer working access to a bench ECU
for NefMoto flasher development, including bootmode, with remote power control.

## Topology: bare-metal Windows next to the ECU

Use a **dedicated, disposable Windows box with the K-line cable plugged
directly into it**, reached over Tailscale + RDP. Two alternatives don't work
well here:

- **A Raspberry Pi with ser2net, RFC2217 or USB/IP.** The flasher is
  Windows-only (WPF, .NET 10 Desktop Runtime x64), and it uses WMI device
  enumeration, which doesn't see network-bridged ports. Bootmode is also
  timing-sensitive: the C167 bootstrap loader auto-bauds off a single byte,
  then takes a block upload at 57600. Adding network jitter causes
  *intermittent* failures, which are the worst kind to debug remotely.
- **A Windows VM.** This is fine if the host can pass through a whole USB
  controller (e.g. Proxmox PCIe passthrough). Per-device passthrough in VMware
  Workstation adds timing indirection. Hyper-V can't pass a serial USB device
  through at all.

An N100 mini PC or an old laptop is enough. A laptop's battery doubles as a
UPS, which protects a flash in progress. Windows **Home has no RDP server**:
use Pro, or RustDesk/Parsec over Tailscale.

Use the Pi (or a smart plug) **only for out-of-band power**: switching mains
to the Windows box and the bench supply, so a wedged machine can be recovered
without anyone on site.

## Cable

| Cable | Status |
|---|---|
| Dumb KKL / K+DCAN, genuine FTDI or CH340 | **Supported.** Cheap; buy one of each to exercise both code paths |
| Ross-Tech **HEX-USB** / **HEX-USB+CAN** (legacy) | **Supported** with Ross-Tech VCP drivers and smart mode disabled |
| Ross-Tech HEX-V2 / HEX-NET | **Not supported.** No dumb K-line pass-through |
| KII-USB | Avoid (poor pass-through) |
| Anything labelled "KWP2000" | Avoid. Counterfeit FTDI, blacklisted by the stock driver |

**With a HEX-USB+CAN, keep VCDS off the bench box.** If VCDS leaves the cable
in smart mode, the flasher can't talk to it, and the remote developer can't fix
that.

Don't connect two cables to the K-line at the same time. Select between them
with a relay.

## Harness and relays

The wiring itself — connector pinout, the minimum bench circuit, the boot-mode
tap and the pre-power-up checks — is in
[bench-harness.md](bench-harness.md). Summary of the relay channels:

Use **normally-open** relays throughout. If the controller dies, the ECU then
ends up powered off and out of bootmode.

| Channel | Switches | Notes |
|---|---|---|
| 1 | Pin 62, terminal 30 (constant 12 V) | Current-limited bench PSU (~2 A) plus a 3 A fuse |
| 2 | Pin 3, terminal 15 (ignition) | Kept separate from 30, so the key can be cycled without cutting power |
| 3 | Boot pin, through 1 kΩ to ground | **Pin 24 of the flash chip**, inside the opened ECU — not a connector pin. It is a data line, so the relay must open again 2–3 s after power-up |
| 4 | K-line cable select | Switches between FTDI/CH340/HEX cables |

Drive the relays from a **USB relay board on the Windows box itself**, so the
developer can script "assert boot pin, then power on". Bootmode entry depends
on timing relative to power-up.

Also:

- A **per-port switchable USB hub** (`uhubctl`-compatible, or a YKUSH) lets the
  developer power-cycle a wedged cable remotely.
- Turn off USB selective suspend and USB port power management.
- Add LEDs on 30/15/boot plus a cheap webcam, or an INA219 current sensor, so
  the developer can see the ECU's actual state.
- Connect no loads (injectors, coils). The real unrecoverable failures are
  electrical.

## Recoverability

Bootmode runs from the C167 mask ROM whatever is in flash. If the boot pin and
power can be switched remotely, **any bad flash or EEPROM write can be
recovered remotely**. That is why the boot pin goes on a relay rather than a
jumper.

Before handing the bench over:

- Read and hash the **current** flash and EEPROM, and store the hashes off the
  bench machine. This captures the tuned state as it is now, not just stock.
- Keep the stock images as a second fallback.
- Consider a spare ECU of the same part number.
- Use `me7_95040.py` to validate every EEPROM read before trusting it.

## Access hygiene

Treat the bench box as compromised from day one:

- A Tailscale ACL allowing **only** the developer's node, to **only** this
  host, on **only** the RDP port. Never port-forward.
- Put it on its own VLAN or guest network, with no route to the home LAN.
- Use a fresh install with no personal credentials, browser sign-ins or cloud
  sync. Image the disk so a restore takes minutes.
- Revoke access by disabling the developer's Tailscale node key.

Pre-install the .NET 10 Desktop Runtime and SDK, git, and the VS Build Tools,
so the developer can deploy their own builds.
