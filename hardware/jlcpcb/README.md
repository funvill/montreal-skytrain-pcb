# JLCPCB outputs

Generated 2026-10-18 11:17 from `montreal-metro-pcb.kicad_pcb` / `.kicad_sch`
with KiCad 10 `kicad-cli` (commands at the bottom). Regenerate after any
board change, with a new timestamp.

| File | Upload as |
|---|---|
| `montreal-skytrain-pcb-2026-10-18-1117-gerbers.zip` | **Gerber file** on the order page: F/B Cu, Paste, Mask, Silk, Edge.Cuts, Excellon drill (PTH + NPTH merged) and the drill map |
| `montreal-skytrain-pcb-2026-10-18-1117-bom-jlcpcb.csv` | **BOM** on the SMT assembly page: `Comment, Designator, Footprint, LCSC Part #` |
| `montreal-skytrain-pcb-2026-10-18-1117-cpl-jlcpcb.csv` | **CPL / pick-and-place**: `Designator, Mid X, Mid Y, Layer, Rotation` |

Assembly is **top side only**, 83 parts, all JLCPCB basic except the LEDs:

| Part | LCSC | Qty |
|---|---|---|
| XL-1615RGBC-WS2812B LED | C5349954 | 73 |
| 1 µF 0402 X5R (ROW0–7; the schematic value still reads "10uF,10V,X5R") | C52923 | 8 |
| 100 µF 6.3 V 1206 X5R bulk capacitor (C1) | C15008 | 1 |
| 330 Ω 0402 data-line resistor (R1) | C25104 | 1 |

Not placed by JLC:

- **U1** (Seeed XIAO RP2040) is a module soldered by hand on the back.
- **SW1–SW4** are DNP; TP1–TP4 are pads for fitting buttons by hand.
- Test points and mounting holes have no part.

`pos-raw.csv` and `bom-raw.csv` are the untouched `kicad-cli` outputs the two
JLC files were derived from.

**Check on the JLC page before ordering:** the LED rotation. JLC's library
orientation for C5349954 may differ from the KiCad footprint's by a constant;
if every LED is off by the same angle in the placement preview, correct the
`Rotation` column by that constant.

Board: 160 × 160 mm, 2 layers, **ENIG** (the exposed-copper water is the
artwork; HASL works but reads silver).

```
kicad-cli pcb export gerbers montreal-metro-pcb.kicad_pcb -o jlcpcb/gerbers/ \
    -l F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
    --subtract-soldermask --no-x2 --no-netlist --check-zones
kicad-cli pcb export drill montreal-metro-pcb.kicad_pcb -o jlcpcb/gerbers/ \
    --format excellon --excellon-units mm --generate-map --map-format gerberx2
kicad-cli pcb export pos montreal-metro-pcb.kicad_pcb -o jlcpcb/pos-raw.csv \
    --format csv --units mm --side both --exclude-dnp
kicad-cli sch export bom montreal-metro-pcb.kicad_sch -o jlcpcb/bom-raw.csv \
    --fields "Reference,Value,Footprint,LCSC Part,LCSC,DNP" --group-by "Value,Footprint,LCSC Part,LCSC" --exclude-dnp
python ../tools/make_jlcpcb.py jlcpcb 2026-10-18-1117
```
