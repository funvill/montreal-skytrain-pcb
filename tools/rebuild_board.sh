#!/usr/bin/env bash
# Regenerate the KiCad board from the data file, end to end: placement,
# artwork, autoroute, ground stitch, DRC, renders. Run from tools/ in Git Bash.
#
#   FREEROUTING_JAR=/path/to/freerouting-2.5.0.jar ./rebuild_board.sh
#
# Every track is replaced by the autorouter: hand routing does not survive.
# If labels were edited in KiCad, run import_labels.py first.
set -euo pipefail

DATA=../input/montreal-schematic-square.json
PCB=../hardware/montreal-metro-pcb.kicad_pcb
SCH=../hardware/montreal-metro-pcb.kicad_sch
KICAD="/c/Program Files/KiCad/10.0/bin"
: "${FREEROUTING_JAR:?set FREEROUTING_JAR to the Freerouting jar}"
WORK=$(mktemp -d)
quiet() { grep -v "swig/python\|duplicate image handler\|assert" || true; }

python -X utf8 test_montreal_data.py "$DATA" | tail -1
python -X utf8 export_placement.py "$DATA" ../hardware --scale 2.0 | head -1
cp ../hardware/firmware_tables.h ../firmware/include/firmware_tables.h
python -X utf8 place_parts.py "$DATA" ../hardware --scale 2.0 | tail -1
python -X utf8 reposition_board.py "$PCB" ../hardware/leds.csv --board 160 --height 160 --controller 124 122
"$KICAD/kicad-cli.exe" sch export netlist --format kicadsexpr -o ../test-results/netlist.net "$SCH" >/dev/null
python -X utf8 check_led_chain.py ../test-results/netlist.net 73 | tail -1
"$KICAD/python.exe" port_board.py "$PCB" ../test-results/netlist.net ../hardware/leds.csv ../hardware/parts.csv 2>&1 | quiet
python -X utf8 export_art.py "$DATA" "$PCB" --scale 2.0 | tail -1

"$KICAD/python.exe" autoroute.py export "$PCB" "$(cygpath -w "$WORK")\\board.dsn" 2>&1 | quiet | grep -o "[0-9]* art keepouts"
(cd "$WORK" && java -jar "$FREEROUTING_JAR" -de board.dsn -do board.ses -mp 40 --gui.enabled=false > route.log 2>&1)
grep -o "final score: [0-9.]* ([^)]*)" "$WORK/route.log" | tail -1 || echo "router: no summary line - see $WORK/route.log"
"$KICAD/python.exe" autoroute.py import "$PCB" "$(cygpath -w "$WORK")\\board.ses" 2>&1 | quiet | grep -o "removed.*"

drc() { "$KICAD/kicad-cli.exe" pcb drc "$PCB" -o ../test-results/drc.json --format json \
          --severity-error --severity-warning --schematic-parity --refill-zones --save-board >/dev/null; }
drc
"$KICAD/python.exe" stitch_ground.py "$PCB" U1 13 2>&1 | quiet | tail -1
drc
python -X utf8 - <<'EOF'
import collections, json
d = json.load(open("../test-results/drc.json"))
print("DRC violations:", dict(collections.Counter(v["type"] for v in d["violations"])) or "none",
      "| unconnected:", len(d["unconnected_items"]),
      "| schematic parity:", len(d.get("schematic_parity", [])))
for v in d["unconnected_items"]:
    print("  unconnected:", " <-> ".join(i["description"][:50] for i in v["items"]))
EOF
python -X utf8 render_board.py "$PCB" ../test-results --kicad-cli "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe" | tail -2
rm -rf "$WORK"
