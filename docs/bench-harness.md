# Bench harness for the ME7.1.1 reference ECU

Wiring for running `4Z7907551S` (Bosch `0 261 208 288`, ME7.1.1, 121-pin
Motronic connector) on the bench: normal K-line flashing, and boot mode.

This is the physical layer under [remote-bench.md](remote-bench.md), which
covers the remote-access topology, the cable choice and the relay strategy.

> **The boot pin is not a connector pin.** "Pin 24" in every ME7 boot-mode
> write-up means **pin 24 of the flash chip**, inside the opened ECU — not
> pin 24 of the 121-pin plug. See [Boot mode](#boot-mode) below.

## Safety rules

1. **Regulated supply, 13.5–14.0 V DC, 3 A or more.** Below 12.0 V the
   bootloader and the KWP2000 session both abort mid-transfer. A bench PSU
   with a current limit is worth more here than a big one.
2. **Fuse the positive line**, 2 A or 3 A fast-blow. The ECU alone draws well
   under 1 A with no loads attached.
3. **One common ground.** The ECU grounds, the PSU negative and the K-line
   cable's ground must meet at a single point. On a KKL/OBD cable that is
   OBD-II pins 4 and 5.
4. **Connect no loads.** No injectors, no coils, no O2 heaters, no secondary
   air pump. The ECU boots and talks with none of them, and the real
   unrecoverable bench failures are electrical.

## Pinout

The connector is numbered 1–121. On the C5 A6 2.7T only pins 1–118 are
populated; 119–121 are empty.

### What the harness needs

| Function | Pin | Wire in the car | Confidence |
|---|---|---|---|
| Ground (terminal 31) | **1** and **2** | BRN, BRN → G12 | Confirmed, two sources |
| Constant +12 V (terminal 30) | **62** | RED, straight off battery + | Confirmed, two sources |
| Switched +12 V ("ignition") | **3** | BLK/BLU, 20 A fuse | See [the pin 3 question](#the-pin-3-question) |
| K-line | **43** | GRN/BLK, spliced to GRN/RED at the DLC → OBD-II pin 7 | Confirmed, three sources |

That is the whole harness. Four wires plus the K-line cable.

### Also worth knowing

Not needed on the bench, but these come up when reading the diagrams:

| Function | Pin | Notes |
|---|---|---|
| Not used | 7, 8 | Marked "PINS 7 & 8 NOT USED" on the factory diagram |
| Power-supply / fuel-pump relay coil | 65 | RED/BLU to relay terminal S. The ECU switches its own relay; the relay feeds injectors, coils and heaters, not the ECU's logic supply |
| CAN low | 58 | ORG/BRN |
| CAN high | 60 | ORG/BLK |
| Crash signal | 67 | VIO/BLU, from the airbag module |
| Instrument cluster | — | Via the K-line splice; **not needed**, the immobiliser is off in flash on this ECU (see [immo-off.md](immo-off.md)) |

The VAG colour convention is orange/brown = CAN-L, orange/black = CAN-H,
which is how 58 and 60 are assigned above. The Nefmoto wiki's VR6 table has
these two the other way round; the factory wire colours and transpondery.com
agree against it. CAN is irrelevant to Nefmoto flashing, which is K-line only,
so this only matters if the bench is later extended.

### The pin 3 question

The sources disagree on which supply pin is the switched one, and the
disagreement is worth understanding before the first power-up.

- **Nefmoto's wiki**, in a table specifically for the 2.7T (B5 S4 / C5 A6 /
  allroad), gives ground on 1 and 2, **switched ignition on pin 3**, and
  **constant battery on pins 15 and 62**.
- **The factory diagram** for the 2003 A6 2.7T shows pin 3 fed BLK/BLU from
  fuse 32 (20 A) in a block headed "hot at all times", pin 62 fed RED directly
  from the battery, and **pin 15 with nothing on it**. The ignition switch's
  output goes to the power-supply relay's terminal 15, not to the ECU.

So pin 62 is certainly permanent, and pin 15 is certainly empty on this car —
don't feed it. Pin 3 is a second 12 V feed whose switched/permanent status is
not settled by the drawings.

**Wire it as the switched rail anyway.** It is what the 2.7T-specific
reference says, it is the only candidate left, and nothing is at risk: both
pins are supply inputs either way. If the ECU turns out not to wake with only
pin 3 switching, fall back to **switching both rails together** — ground the
ECU, then apply 12 V to 3 and 62 at the same moment. The C167 samples the boot
pin at reset, so a single-rail power-up enters boot mode just as well; the
only thing lost is the ability to cycle the "key" without dropping terminal 30.

## Minimum bench circuit

```
  PSU +13.5 V ──┬── 3 A fast-blow ──┬── [relay 1, NO] ── ECU pin 62   (term 30)
                │                   │
                │                   └── [relay 2, NO] ── ECU pin 3    (term 15)
                │
  PSU −  ───────┼───────────────────┬── ECU pin 1
                │                   ├── ECU pin 2
                │                   ├── OBD-II pin 4 + pin 5
                │                   └── [relay 3, NO] ── 1 kΩ ── flash chip pin 24
                │
             (single star point — one bolt or one bus bar)

  K-line cable ── OBD-II pin 7 ───────── ECU pin 43
                  OBD-II pin 16 ──────── +12 V (only if the cable needs it)
```

Some KKL cables take their own power from OBD-II pin 16; a genuine FTDI one
usually runs off USB. Check before wiring it — a cable that back-feeds 12 V
into a pin 16 you left floating is a confusing fault to chase.

Wire gauge is uncritical at these currents; 20 AWG is plenty. What matters is
the connector end.

### The connector

Harvest a **121-pin pigtail from a scrap engine harness** rather than buying
loose terminals. Cut it with 150 mm of wire on every pin, label pins 1, 2, 3,
43 and 62, and cut the rest back — don't strip them. The terminals are small
and awkward to crimp individually, and a wrong crimp that half-seats will
intermittently drop a supply mid-flash, which is exactly the failure that
corrupts a write.

If you build it from loose terminals instead, confirm the terminal part number
against the actual connector housing in hand; the 121-pin shell uses more than
one terminal size across its chambers.

## Relay channel map

This supersedes the table in [remote-bench.md](remote-bench.md). All relays
**normally open**, so a dead controller leaves the ECU powered off and out of
boot mode.

| Channel | Switches | Notes |
|---|---|---|
| 1 | Pin 62 (terminal 30) | Through the 3 A fuse |
| 2 | Pin 3 (terminal 15) | Separate, so the "key" can be cycled without dropping 30 |
| 3 | Boot pin tap, through 1 kΩ to ground | Must open again a few seconds after power-up |
| 4 | K-line cable select | Between the FTDI/CH340 and HEX-USB+CAN cables |

Drive them from a USB relay board on the bench Windows box itself, so the
sequence "close 3, close 1+2, wait, open 3" can be scripted. Boot mode depends
on that timing.

## Boot mode

The ECU has to be **open** for this. The boot pin is a leg of the flash chip.

### Finding it

From the Nefmoto and S4wiki write-ups (identical text, credited to
NOTORIOUSVR), verbatim:

> Connect PIN 24 on the flash chip (800BB) to ground before turning on your
> switch/ignition signal.

and, on locating it:

> PIN 24 the the 2nd one in from the left side on the bottom. The chip when
> you're looking at it should have a circle in the top right hand corner
> (indicating PIN 1). Also the ECU's plugs will be facing to the RIGHT!

So: ECU open, connectors to the right, flash chip's pin-1 dot at top right,
count two in from the left along the bottom row.

### What it does

S4wiki: *"Grounding pin 24 on the flash also grounds the P0L.4 pin (Port 0,
bit 4) on the CPU"*, and *"The CPU samples this pin on power up. If it sees
low, it will go into boot mode."* That is the C167 bootstrap loader entry
condition.

The thing to take from this: **pin 24 is a bus line**, shared between the
flash and the CPU. On a 44-pin PSOP Am29F800B, package pin 24 is DQ12. It
carries data the moment the CPU starts fetching. That is why it is grounded
only across reset and released immediately afterwards — and why this channel
has to be a relay and not a jumper on a remote bench.

### Sequence

1. Permanent rail (pin 62) on, "ignition" (pin 3) off.
2. Close the boot relay — pin 24 pulled towards ground through 1 kΩ.
3. Turn on pin 3.
4. Wait 2–3 seconds.
5. **Open the boot relay.**

S4wiki is explicit about step 5: *"DO NOT leave this pin shorted to ground
while you are programming the device; it will fail."* and *"It only has to be
grounded while the ECU is 'powering' up."*

### The resistor

Neither wiki specifies one; both say "ground". The forum threads disagree, and
the values reported as working range from 1 kΩ to 10 kΩ, with several people
insisting a bare wire is what kills ECUs and at least one reporting a bare
wire used for years without trouble.

**Use 1 kΩ.** The reasoning, not an appeal to authority: at reset nothing is
driving the line, so even 10 kΩ pulls it low reliably; but if the timing slips
and the CPU has started fetching, 1 kΩ limits the fight with a driven output
to a few milliamps, where a bare wire would be a dead short across a push-pull
driver. 1 kΩ is low enough to win at reset and high enough to survive getting
it wrong. If boot mode won't take with 1 kΩ, drop to 470 Ω before considering
a bare wire.

### Making the tap

Solder a 30 AWG flying lead to the leg and strain-relieve it to the board with
a dab of hot glue, then bring it out of the case to the relay. A test clip or
pogo pin is fine for a one-off on the bench, but not for a bench someone is
driving remotely — the whole point of the relay channel is that nobody has to
be standing there.

### Board variants

Some ME7.1.1 boards reportedly carry a zero-ohm ("000") resistor that has to
be removed before boot mode works, and others specifically must *not* have it
removed. This is forum-level information, it is not in either wiki, and it has
**not** been checked against this ECU's board. Inspect before assuming, and
try boot mode as-is first — if it enters, there is nothing to remove.

## Before the first power-up

With the PSU off and nothing connected:

1. Continuity from the harness ground lead to pins 1 and 2, and to OBD-II
   pins 4 and 5. Should be a dead short through the star point.
2. Continuity from the 12 V lead to pins 3 and 62 **only**. Probe pins 15, 21
   and 121 and confirm they are open.
3. Resistance between the 12 V lead and ground: open circuit. A reading of a
   few ohms means a crimp has shorted in the connector shell.
4. PSU on with the harness **unplugged from the ECU**, current limit set to
   ~1 A. Measure 13.5 V between the 12 V lead and ground, correct polarity,
   at the connector pins themselves.
5. Plug in, power up. Idle draw should be well under 500 mA. Anything above
   that, or a rising current, means power off now.

Then: `me7_flash_info.py` on the flash you read back, and `me7_95040.py` on
the EEPROM, before trusting either image. Hash both and keep them off the
bench machine — see [remote-bench.md](remote-bench.md).

## Sources

- **Factory wiring diagram, 2003 Audi A6 2.7T**, "Motronic Engine Control
  Module (ECM)", sheets 157104 / 157106 / 157108. Mirrored on the rusEFI wiki
  at `github.com/rusefi/rusefi/wiki/VAG-C5#2003-a6-27t` as three scans. This
  is the only source here that is per-pin for this exact car, and every
  "confirmed" row above was read off it.
- **Nefmoto wiki, ECU pin outs** —
  `nefariousmotorsports.com/wiki/ECU_pin_outs`. The 2.7T bench table and the
  three safety rules. Credits Tony's S4 pinouts thread and Matt Danger's bench
  flashing guide.
- **Nefmoto wiki, ECU Boot Mode** and **S4wiki, Boot mode** —
  `nefariousmotorsports.com/wiki/ECU_Boot_Mode`,
  `s4wiki.com/wiki/Boot_mode`. Same text, credited to NOTORIOUSVR. Source of
  every boot-mode quotation above.
- **transpondery.com**, VAG ME7.x basic connection — GND 1, VCC 3/21/62,
  K-line 43, CAN-H 60, CAN-L 58 for the 121-pin ME7.1/7.1.1/7.5. Corroborates
  the K-line and CAN pins.
- **rusEFI forum, "Hellen 121 ME7 for VAG PnP ECU"** (`rusefi.com/forum`,
  topic 1931). A factory-diagram read-through by a contributor gives the 2.7T
  as 20 A into pin 3 with pins 21, 23 and 121 unused, against a board-design
  proposal in the same thread that wanted 121 as the main 12 V input. The
  thread never resolves it; the C5 diagram above does, for this car.

Sources disagree on pin 15 (Nefmoto: constant 12 V; factory diagram: not
connected) and on CAN polarity. Where they disagree, the factory diagram for
this chassis wins, and the disagreement is called out above rather than
averaged away.
