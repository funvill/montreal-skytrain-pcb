# Hardware (KiCad 10)

`montreal-metro-pcb` — 160 × 160 mm, 2 layers, 73 WS2812B LEDs (XL-1615), one
per station, generated from `../input/montreal-schematic-square.json`.

Copied from the Vancouver SkyTrain v3 project and ported by the scripts in
`../tools`. **The board is placed, has its artwork and is autorouted; DRC is clean.**

## State

| | |
|---|---|
| Schematic | 73 LEDs. LED69–73 were added by `add_schematic_leds.py`; chain and power verified from KiCad's netlist by `check_led_chain.py` |
| Board vs schematic | 0 parity issues (`kicad-cli pcb drc --schematic-parity`) |
| Placement | LEDs at their stations, each turned so DOUT faces the next LED; 8 capacitors on the front in spots clear of labels, routes and water; XIAO and buttons on the back at (124, 122) mm, away from the downtown LEDs whose vias their pads would block; M3 holes 4 mm in from each corner |
| Artwork | Water (bare copper), routes, station rings and labels, wordmark — written by `export_art.py` |
| Routing | Freerouting 2.5.0, via `autoroute.py`: 944 track segments, 82 vias. +5V is 0.5 mm, signals 0.25 mm. Ground is the pour on both sides; every ground pad on the front has its own via to the back pour |
| DRC | 0 violations, 0 unconnected items, 0 schematic parity issues |
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

The water is bare copper on the front with no net, and KiCad does not export
graphic copper to the autorouter. `autoroute.py export` therefore covers the
front artwork with track-and-via keepouts on a throwaway copy of the board,
and tells the router the ground plane is on the back only.

```
"C:/Program Files/KiCad/10.0/bin/python.exe" autoroute.py export ../hardware/montreal-metro-pcb.kicad_pcb OUT.dsn
java -jar freerouting-2.5.0.jar -de OUT.dsn -do OUT.ses -mp 40 --gui.enabled=false
"C:/Program Files/KiCad/10.0/bin/python.exe" autoroute.py import ../hardware/montreal-metro-pcb.kicad_pcb OUT.ses
kicad-cli pcb drc ... --refill-zones --save-board          # see Checking
"C:/Program Files/KiCad/10.0/bin/python.exe" stitch_ground.py ../hardware/montreal-metro-pcb.kicad_pcb U1 13
```

`import` replaces every track, so re-routing is repeatable; any hand routing
is lost. The last step ties U1's ground pad into the back pour: its
neighbouring pads are too close for the pour to reach it.

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

1. Review the autorouted tracks. About 70 % of the track length is on the
   front, where it cuts visible channels in the ground pour.
2. Check U1's orientation (USB-C toward a board edge) and the test-point
   positions on the back.
3. New back-side artwork, if wanted.
4. Hand pass on the labels in KiCad, then `import_labels.py`.
5. DRC, then fabrication outputs (`make_jlcpcb.py`). ENIG finish, so the bare
   copper reads gold.
