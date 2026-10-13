# Hardware (KiCad 10)

`montreal-metro-pcb` — 160 × 160 mm, 2 layers, 73 WS2812B LEDs (XL-1615), one
per station, generated from `../input/montreal-schematic-square.json`.

Copied from the Vancouver SkyTrain v3 project and ported by the scripts in
`../tools`. **The board is placed and has its artwork, but is not routed.**

## State

| | |
|---|---|
| Schematic | 73 LEDs. LED69–73 were added by `add_schematic_leds.py`; chain and power verified from KiCad's netlist by `check_led_chain.py` |
| Board vs schematic | 0 parity issues (`kicad-cli pcb drc --schematic-parity`) |
| Placement | LEDs at their stations, each turned so DOUT faces the next LED; 8 capacitors on the front in spots clear of labels, routes and water; XIAO and buttons centred on the back; M3 holes 4 mm in from each corner |
| Artwork | Water (bare copper), routes, station rings and labels, wordmark — written by `export_art.py` |
| DRC | No clearance, edge-clearance, short or courtyard violations. 170 unconnected items: **nothing is routed yet** |
| Back side | The Vancouver moon-phase artwork was removed: it is 191 mm wide and does not fit this board |

## Regenerating

From `../tools`, after any change to the data file:

```
python export_placement.py ../input/montreal-schematic-square.json ../hardware --scale 2.0
python place_parts.py      ../input/montreal-schematic-square.json ../hardware --scale 2.0
python reposition_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../hardware/leds.csv --board 160 --height 160
kicad-cli sch export netlist --format kicadsexpr -o ../test-results/netlist.net ../hardware/montreal-metro-pcb.kicad_sch
"C:/Program Files/KiCad/10.0/bin/python.exe" port_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../test-results/netlist.net ../hardware/leds.csv ../hardware/parts.csv
python export_art.py       ../input/montreal-schematic-square.json ../hardware/montreal-metro-pcb.kicad_pcb --scale 2.0
```

`port_board.py` moves LEDs and re-aims them, so once tracks exist, re-running
it after moving a station will leave those tracks behind. Do not pass
`--strip` again: that removes every track and all front artwork.

**If labels have been edited by hand in KiCad, run `import_labels.py` before
`export_art.py`**, or the exporter overwrites them.

## Checking

```
python check_led_chain.py ../test-results/netlist.net 73
kicad-cli pcb drc ../hardware/montreal-metro-pcb.kicad_pcb -o ../test-results/drc.json --format json --severity-error --severity-warning --schematic-parity --refill-zones --save-board
python render_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../test-results --kicad-cli "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
```

## Still to do

1. **Route** the data chain and power. The water is bare copper on the front
   with no net, so front-side tracks cannot cross it.
2. Check U1's orientation (USB-C toward a board edge) and the test-point
   positions on the back.
3. New back-side artwork, if wanted.
4. Hand pass on the labels in KiCad, then `import_labels.py`.
5. DRC, then fabrication outputs (`make_jlcpcb.py`). ENIG finish, so the bare
   copper reads gold.
