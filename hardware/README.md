# Hardware (KiCad 10)

`montreal-metro-pcb` — 160 × 160 mm, 2 layers, 73 WS2812B LEDs (XL-1615), one
per station, generated from `../input/montreal-schematic-square.json`.

Copied from the Vancouver SkyTrain v3 project and ported by the scripts in
`../tools`. **The board is placed and has its artwork. It is not routed: routing is done by hand.**

## State

| | |
|---|---|
| Schematic | 73 LEDs. LED69–73 were added by `add_schematic_leds.py`; chain and power verified from KiCad's netlist by `check_led_chain.py` |
| Board vs schematic | 0 parity issues (`kicad-cli pcb drc --schematic-parity`) |
| Placement | LEDs at their stations, each turned so DOUT faces the next LED; 8 capacitors on the front in spots clear of labels, routes and water; XIAO and buttons on the back at (124, 122) mm, away from the downtown LEDs whose vias their pads would block; M3 holes 4 mm in from each corner |
| Artwork | Water (bare copper), routes, station rings and labels, wordmark — written by `export_art.py` |
| Labels | Placed by hand in KiCad (2026-10-13) and frozen in `../input/label_overrides-square.json`; every build re-applies them |
| Routing | **None.** The tracks are to be routed by hand. An autorouted version (Freerouting, DRC-clean) is in git history at `b02ee1b` for reference |
| DRC | No clearance, edge, short or courtyard violations; every net is unconnected until routed |
| Back side | The Vancouver moon-phase artwork was removed: it is 191 mm wide and does not fit this board |

## Regenerating

From `../tools`, after any change to the data file:

```
python export_placement.py ../input/montreal-schematic-square.json ../hardware --scale 2.0
python place_parts.py      ../input/montreal-schematic-square.json ../hardware --scale 2.0
python reposition_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../hardware/leds.csv --board 160 --height 160 --controller 124 122
kicad-cli sch export netlist --format kicadsexpr -o ../test-results/netlist.net ../hardware/montreal-metro-pcb.kicad_sch
"C:/Program Files/KiCad/10.0/bin/python.exe" port_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../test-results/netlist.net ../hardware/leds.csv ../hardware/parts.csv
python export_art.py       ../input/montreal-schematic-square.json ../hardware/montreal-metro-pcb.kicad_pcb --scale 2.0
```

Use the same `reposition_board.py` arguments every time, including
`--controller 124 122`.

## Routing

Routing is manual. The water is bare copper on the front with no net, so
front-side tracks must not cross it; ground pads on the front each need a
via to the back pour, because the front pour is cut into islands by the
artwork. `U1` pad 13 (GND) sits between two pads closer than the pour's
clearance, so the pour will not reach it: give it a track.

`rebuild_board.sh` leaves tracks alone. `rebuild_board.sh --autoroute`
replaces **every** track with the autorouter's (`autoroute.py`,
`stitch_ground.py`); `autoroute.py clear` removes them all.

## After editing labels in KiCad

```
python import_labels.py ../input/montreal-schematic-square.json ../hardware/montreal-metro-pcb.kicad_pcb
python save_label_overrides.py ../input/montreal-schematic-square.json ../input/label_overrides-square.json
```

Do this before any rebuild, or the exporter writes the old labels back.

`port_board.py` moves LEDs and re-aims them, so once tracks exist, re-running
it after moving a station will leave those tracks behind. Do not pass
`--strip` again: that removes every track and all front artwork.

Or run the whole thing, placement through renders, in one go (Git Bash, from
`../tools`); it does not touch tracks:

```
./rebuild_board.sh
```

## Checking

```
python check_led_chain.py ../test-results/netlist.net 73
kicad-cli pcb drc ../hardware/montreal-metro-pcb.kicad_pcb -o ../test-results/drc.json --format json --severity-error --severity-warning --schematic-parity --refill-zones --save-board
python render_board.py ../hardware/montreal-metro-pcb.kicad_pcb ../test-results --kicad-cli "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
```

## Still to do

1. **Route the board** (by hand).
2. Check U1's orientation (USB-C toward a board edge) and the test-point
   positions on the back.
3. New back-side artwork, if wanted.
5. DRC, then fabrication outputs (`make_jlcpcb.py`). ENIG finish, so the bare
   copper reads gold.
