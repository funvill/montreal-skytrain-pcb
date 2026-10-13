"""Reduce osm/stations.json to montreal_station_latlon.json and write the
montreal.json skeleton (lines, station names - no positions, labels or chain).

The line definitions below are the hand-authored station list: every name is
matched against an OSM node (accent/apostrophe-insensitive) and the script
fails if one is missing, so a typo here cannot silently drop an LED.

Scope (decided): the four metro lines plus the five Blue line extension
stations under construction (2031). OSM has no station nodes for those yet,
so their positions are derived from osm/blue_extension.json: the
intersection of rue Jean-Talon Est with each cross street, and the Anjou
entrance building's footprint. They carry "future": true.

The REM is out of scope; pass "rem" to include it (two REM stations share a
name with a metro station and get a "-rem" id suffix).

Also holds the hand-authored parts of the data file: label wrapping / short
names (French names are hyphenated, so citymap's split-at-the-dash default
is wrong for them) and the LED CHAIN order.

Run:  python build_station_latlon.py [metro|rem]
"""
import json
import re
import sys
import unicodedata

SCOPE = sys.argv[1] if len(sys.argv) > 1 else "metro"   # "metro" or "rem" (= metro + REM)
SHARE_REM_LED = False

METRO = [
    ("green", "Ligne verte", "#008E4F", [[
        "Angrignon", "Monk", "Jolicoeur", "Verdun", "De l'Église", "LaSalle",
        "Charlevoix", "Lionel-Groulx", "Atwater", "Guy-Concordia", "Peel",
        "McGill", "Place-des-Arts", "Saint-Laurent", "Berri-UQAM", "Beaudry",
        "Papineau", "Frontenac", "Préfontaine", "Joliette", "Pie-IX", "Viau",
        "Assomption", "Cadillac", "Langelier", "Radisson", "Honoré-Beaugrand"]]),
    ("orange", "Ligne orange", "#EF8122", [[
        "Côte-Vertu", "Du Collège", "De La Savane", "Namur", "Plamondon",
        "Côte-Sainte-Catherine", "Snowdon", "Villa-Maria", "Vendôme",
        "Place-Saint-Henri", "Lionel-Groulx", "Georges-Vanier",
        "Lucien-L'Allier", "Bonaventure", "Square-Victoria-OACI",
        "Place-d'Armes", "Champ-de-Mars", "Berri-UQAM", "Sherbrooke",
        "Mont-Royal", "Laurier", "Rosemont", "Beaubien", "Jean-Talon", "Jarry",
        "Crémazie", "Sauvé", "Henri-Bourassa", "Cartier", "De la Concorde",
        "Montmorency"]]),
    ("yellow", "Ligne jaune", "#FFE300", [[
        "Berri-UQAM", "Jean-Drapeau", "Longueuil–Université-de-Sherbrooke"]]),
    ("blue", "Ligne bleue", "#0083CA", [[
        "Snowdon", "Côte-des-Neiges", "Université-de-Montréal",
        "Édouard-Montpetit", "Outremont", "Acadie", "Parc", "De Castelnau",
        "Jean-Talon", "Fabre", "D'Iberville", "Saint-Michel", "Vertières",
        "Mary-Two-Axe-Earley", "Césira-Parisotto", "Madeleine-Parent", "Anjou"]]),
]
# Blue line extension: station -> cross street of rue Jean-Talon Est, or the
# name of the OSM way whose footprint is the station.
FUTURE = {
    "Vertières": "Boulevard Pie-IX",
    "Mary-Two-Axe-Earley": "Boulevard Viau",
    "Césira-Parisotto": "Boulevard Lacordaire",
    "Madeleine-Parent": "Boulevard Langelier",
    "Anjou": "Station Anjou - Édicule Principale - Ligne Bleue",
}
# Label text. wrap = explicit lines (hyphen kept at the line end); short =
# what the optimiser may fall back to where the full name has no room.
WRAP = {
    "Longueuil–Université-de-Sherbrooke": ["Longueuil–", "Université-de-", "Sherbrooke"],
    "Côte-Sainte-Catherine": ["Côte-Sainte-", "Catherine"],
    "Université-de-Montréal": ["Université-", "de-Montréal"],
    "Square-Victoria-OACI": ["Square-", "Victoria-OACI"],
    "Mary-Two-Axe-Earley": ["Mary-Two-", "Axe-Earley"],
    "Édouard-Montpetit": ["Édouard-", "Montpetit"],
    "Place-Saint-Henri": ["Place-", "Saint-Henri"],
    "Honoré-Beaugrand": ["Honoré-", "Beaugrand"],
    "Césira-Parisotto": ["Césira-", "Parisotto"],
    "Madeleine-Parent": ["Madeleine-", "Parent"],
    "Lucien-L'Allier": ["Lucien-", "L'Allier"],
    "Côte-des-Neiges": ["Côte-des-", "Neiges"],
    "Henri-Bourassa": ["Henri-", "Bourassa"],
    "Georges-Vanier": ["Georges-", "Vanier"],
    "Place-des-Arts": ["Place-", "des-Arts"],
    "De la Concorde": ["De la", "Concorde"],
}
SHORT = {
    "Longueuil–Université-de-Sherbrooke": "Longueuil",
    "Université-de-Montréal": "U. de Montréal",
    "Côte-Sainte-Catherine": "Côte-Ste-Catherine",
    "Square-Victoria-OACI": "Square-Victoria",
    "Place-Saint-Henri": "Place-St-Henri",
}
# LED daisy-chain order - the physical routing order. DRAFT: walks each line
# end to end with three jumps (Honoré-Beaugrand -> Anjou, Montmorency ->
# Côte-Vertu, Angrignon -> Villa-Maria). Revisit once the controller
# position is fixed.
CHAIN = [
    "Longueuil–Université-de-Sherbrooke", "Jean-Drapeau", "Berri-UQAM",
    "Beaudry", "Papineau", "Frontenac", "Préfontaine", "Joliette", "Pie-IX",
    "Viau", "Assomption", "Cadillac", "Langelier", "Radisson", "Honoré-Beaugrand",
    "Anjou", "Madeleine-Parent", "Césira-Parisotto", "Mary-Two-Axe-Earley",
    "Vertières", "Saint-Michel", "D'Iberville", "Fabre", "Jean-Talon",
    "Jarry", "Crémazie", "Sauvé", "Henri-Bourassa", "Cartier", "De la Concorde",
    "Montmorency",
    "Côte-Vertu", "Du Collège", "De La Savane", "Namur", "Plamondon",
    "Côte-Sainte-Catherine", "Snowdon", "Côte-des-Neiges",
    "Université-de-Montréal", "Édouard-Montpetit", "Outremont", "Acadie",
    "Parc", "De Castelnau", "Beaubien", "Rosemont", "Laurier", "Mont-Royal",
    "Sherbrooke", "Champ-de-Mars", "Place-d'Armes", "Square-Victoria-OACI",
    "Bonaventure", "Lucien-L'Allier", "Georges-Vanier", "Lionel-Groulx",
    "Charlevoix", "LaSalle", "De l'Église", "Verdun", "Jolicoeur", "Monk",
    "Angrignon",
    "Villa-Maria", "Vendôme", "Place-Saint-Henri", "Atwater", "Guy-Concordia",
    "Peel", "McGill", "Place-des-Arts", "Saint-Laurent",
]
REM = [
    ("rem", "REM", "#84BD00", [
        ["Brossard", "Du Quartier", "Panama", "Île-des-Soeurs", "Gare Centrale",
         "McGill", "Édouard-Montpetit", "Canora", "Ville-de-Mont-Royal",
         "Côte-de-Liesse", "Montpellier", "Du Ruisseau", "Bois-Franc",
         "Sunnybrooke", "Pierrefonds-Roxboro", "Île-Bigras", "Sainte-Dorothée",
         "Grand-Moulin", "Deux-Montagnes"],
        ["Bois-Franc", "Des Sources", "Fairview-Pointe-Claire", "Kirkland",
         "Anse-à-l'Orme"],
        ["Bois-Franc", "Marie-Curie", "YUL-Aéroport-Montréal-Trudeau"]]),
]


def slug(name):
    s = unicodedata.normalize("NFKD", name.replace("œ", "oe"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"^station\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def is_rem(tags):
    return tags.get("network") == "REM"


# OSM nodes -> {(slug, is_rem): [(lat, lon), ...]}; big stations are tagged twice
nodes = {}
for e in json.load(open("osm/stations.json", encoding="utf-8"))["elements"]:
    t = e.get("tags", {})
    if "name" in t:
        nodes.setdefault((slug(t["name"]), is_rem(t)), []).append((e["lat"], e["lon"]))

# Blue line extension positions from the cached street / footprint geometry
_ext = {}
for e in json.load(open("osm/blue_extension.json", encoding="utf-8"))["elements"]:
    _ext.setdefault(e["tags"].get("name"), {}).update(
        {n: (g["lat"], g["lon"]) for n, g in zip(e["nodes"], e["geometry"])})
_jt = _ext["Rue Jean-Talon Est"]
for name, src in FUTURE.items():
    pts = [p for n, p in _ext[src].items() if src.startswith("Station") or n in _jt]
    assert pts, f"no geometry for future station {name!r}"
    nodes[(slug(name), False)] = pts

latlon, stations, lines = {}, {}, []
for group, rem in ((METRO, False), (REM, True)):
    if rem and SCOPE != "rem":
        continue
    for lid, lname, color, paths in group:
        out_paths = []
        for path in paths:
            ids = []
            for name in path:
                key = (slug(name), rem)
                assert key in nodes, f"{lid}: no OSM node for {name!r}"
                sid = key[0]
                if rem and (sid, False) in nodes and not SHARE_REM_LED:
                    sid += "-rem"
                pts = nodes[key]
                latlon[sid] = [round(sum(p[0] for p in pts) / len(pts), 6),
                               round(sum(p[1] for p in pts) / len(pts), 6)]
                st = stations.setdefault(sid, {"name": name})
                if name in FUTURE:
                    st["future"] = True
                if name in SHORT:
                    st["short"] = SHORT[name]
                if name in WRAP:
                    st["wrap"] = WRAP[name]
                ids.append(sid)
            out_paths.append(ids)
        lines.append({"id": lid, "name": lname, "color": color, "paths": out_paths})

used = {}
for line in lines:
    for sid in {s for p in line["paths"] for s in p}:
        used[sid] = used.get(sid, 0) + 1
for sid, n in used.items():
    if n > 1:
        stations[sid]["interchange"] = True

unused = sorted(k for k in nodes if (SCOPE == "rem" or not k[1]) and
                not any(k[0] == s.removesuffix("-rem") for s in stations))
json.dump(latlon, open("montreal_station_latlon.json", "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
chain = [slug(n) for n in CHAIN]
if SCOPE == "metro":
    assert sorted(chain) == sorted(stations), (
        f"chain != stations: missing {set(stations) - set(chain)}, "
        f"extra {set(chain) - set(stations)}, {len(chain)} entries")
json.dump({"city": "montreal", "lines": lines, "stations": stations,
           "extras": [], "chain": chain if SCOPE == "metro" else []},
          open("montreal.skeleton.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"scope={SCOPE}: {len(stations)} stations / LEDs, "
      f"{sum(1 for s in stations.values() if s.get('interchange'))} interchanges")
for line in lines:
    print(f"  {line['id']:7s} {len({s for p in line['paths'] for s in p})}")
if unused:
    print("  OSM nodes not on any line:", unused)
