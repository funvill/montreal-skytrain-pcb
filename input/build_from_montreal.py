"""Assemble montreal.json: OSM water-polygon geography (geo_montreal.py),
OSM station positions, copper place names and the wordmark.

Frame and water come from geo_montreal (the approved shape); lines, station
names, label text and the LED chain from montreal.skeleton.json, written by
build_station_latlon.py (the hand-authored station list); positions from
montreal_station_latlon.json. Labels and suppressed_art already in
montreal.json are preserved. Board = BOARD mm per canvas unit, so a
100-unit canvas is a 200 mm-wide board.

Copper furniture: place names as small copper text near a seed point, at
the spot farthest from track, water and other labels, and the MONTRÉAL
wordmark on the largest clear piece of land.

Run:  python build_station_latlon.py && python build_from_montreal.py
      (then ../tools/auto_label.py)
"""
import json
import math
import random

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

import geo_montreal as G

BOARD = 2.0                              # board mm per canvas unit
CANVAS_W = 100.0
SCALE = CANVAS_W / G.W_KM                # canvas units per km
CANVAS_H = round(G.H_KM * SCALE, 2)
MM_PER_KM = SCALE * BOARD
MIN_PITCH = 3.3 / BOARD                  # canvas units; 3.3 mm, not the package's
                                         # 2.5: rotated diagonal neighbours' pads clash
PAD_CLEAR_MM = 2.2
CITY_TEXT_MM = 1.5
TITLE_MM = 8.0


def c(x_km, y_km):
    return (round(x_km * SCALE, 2), round(y_km * SCALE, 2))


def c_inv(cx, cy):
    return (cx / SCALE, cy / SCALE)


import os
sk = json.load(open("montreal.skeleton.json", encoding="utf-8"))
d = json.load(open("montreal.json", encoding="utf-8")) if os.path.exists("montreal.json") else {}
old = d.get("stations", {})
d.update(city=sk["city"], lines=sk["lines"], extras=sk["extras"], chain=sk["chain"])
d["stations"] = {sid: {**st, **{k: v for k, v in old.get(sid, {}).items() if k == "label"}}
                 for sid, st in sk["stations"].items()}
water = G.water()
land = G.FRAME.difference(water)

# --- stations ------------------------------------------------------------
LL = json.load(open("montreal_station_latlon.json", encoding="utf-8"))
missing = set(d["stations"]) - set(LL)
assert not missing, f"no position for {missing}"
KM = {sid: G.km(*ll) for sid, ll in LL.items()}
for sid, p in KM.items():                # bank stations onto land
    q = Point(p)
    if water.contains(q):
        b = land.boundary.interpolate(land.boundary.project(q))
        vx, vy = b.x - q.x, b.y - q.y
        L = math.hypot(vx, vy) or 1
        KM[sid] = (b.x + vx / L * 0.08, b.y + vy / L * 0.08)
CANVAS = {sid: c(*p) for sid, p in KM.items()}


def push(a, b, min_d):
    dd = math.hypot(b[0] - a[0], b[1] - a[1])
    if dd >= min_d:
        return b
    ux, uy = (b[0] - a[0]) / dd, (b[1] - a[1]) / dd
    return (round(a[0] + ux * min_d, 2), round(a[1] + uy * min_d, 2))


# Downtown runs that are under the pitch floor in reality: spread each
# outward from Berri-UQAM along its own line before the global relaxation.
for chain in [["berri-uqam", "saint-laurent", "place-des-arts", "mcgill", "peel",
               "guy-concordia", "atwater"],
              ["berri-uqam", "champ-de-mars", "place-d-armes", "square-victoria-oaci",
               "bonaventure", "lucien-l-allier", "georges-vanier"],
              ["berri-uqam", "beaudry", "papineau"],
              ["berri-uqam", "sherbrooke", "mont-royal", "laurier"]]:
    for a, b in zip(chain, chain[1:]):
        CANVAS[b] = push(CANVAS[a], CANVAS[b], MIN_PITCH)
ids = list(CANVAS)
for _ in range(60):
    moved = False
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            (ax, ay), (bx, by) = CANVAS[a], CANVAS[b]
            dd = math.hypot(bx - ax, by - ay)
            if dd >= MIN_PITCH - 1e-6:
                continue
            ux, uy = ((bx - ax) / dd, (by - ay) / dd) if dd > 1e-6 else (1.0, 0.0)
            h = (MIN_PITCH - dd) / 2 + 0.01
            CANVAS[a] = (round(ax - ux * h, 2), round(ay - uy * h, 2))
            CANVAS[b] = (round(bx + ux * h, 2), round(by + uy * h, 2))
            moved = True
    if not moved:
        break

for sid, (x, y) in CANVAS.items():
    if sid in d["stations"]:
        d["stations"][sid]["x"], d["stations"][sid]["y"] = x, y
    else:
        for e in d["extras"]:
            if e["id"] == sid:
                e["x"], e["y"] = x, y

routes_km = unary_union([LineString([c_inv(*CANVAS[a]), c_inv(*CANVAS[b])])
                         for line in d["lines"] for path in line["paths"]
                         for a, b in zip(path, path[1:])])
station_pts = unary_union([Point(c_inv(*p)) for p in CANVAS.values()])

# --- water with LED clearance ----------------------------------------------
for cx, cy in CANVAS.values():
    water = water.difference(Point(c_inv(cx, cy)).buffer(PAD_CLEAR_MM / MM_PER_KM, 12))


def ring_with_holes(poly):
    pts = list(poly.exterior.coords)[:-1]
    for ring in poly.interiors:
        hole = list(ring.coords)[:-1]
        if Polygon(hole).area < 0.02:
            continue
        i = min(range(len(pts)), key=lambda k: (pts[k][0] - hole[0][0]) ** 2 +
                (pts[k][1] - hole[0][1]) ** 2)
        pts = pts[:i + 1] + hole + [hole[0]] + [pts[i]] + pts[i + 1:]
    return [list(c(*p)) for p in pts]


geo = [{"name": f"water-{i}", "type": "water", "points": ring_with_holes(g)}
       for i, g in enumerate(sorted(getattr(water, "geoms", [water]), key=lambda p: -p.area))
       if g.area >= 0.02]

# --- place names: (text, lat, lon) seed, searched within SEED_KM ------------
PLACES = []        # none: the board carries the city name only
SEED_KM = 2.5
random.seed(4)
annotations = []
placed = []   # shapely boxes of placed text, km

# Station labels already in montreal.json (hand-placed or annealed) are
# obstacles for the city labels, so a rebuild never drops a city name on
# top of one; leaders count too.
import sys
sys.path.insert(0, "../tools")
import citymap
_tmp = dict(d)
_tmp["canvas_mm"], _tmp["canvas_h_mm"], _tmp["board_scale"] = CANVAS_W, CANVAS_H, BOARD
json.dump(_tmp, open("_tmp_city.json", "w", encoding="utf-8"))
_city = citymap.load("_tmp_city.json")
import os
os.remove("_tmp_city.json")
for st in list(_city.stations.values()) + _city.extras:
    bx = citymap.label_box(st, citymap.TEXT_H, BOARD)
    placed.append(Polygon([(x / MM_PER_KM, y / MM_PER_KM) for x, y in bx]).buffer(0.25))
    seg = citymap.leader_segment(st, BOARD)
    if seg:
        placed.append(LineString([(p[0] / MM_PER_KM, p[1] / MM_PER_KM) for p in seg]).buffer(0.2))
avoid = unary_union([routes_km.buffer(0.35), water.buffer(0.12), station_pts.buffer(0.6)])


def text_box(x, y, text, size_mm, char_w=0.85):
    w = len(text) * char_w * size_mm / MM_PER_KM
    h = 1.3 * size_mm / MM_PER_KM
    return box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)


# --- wordmark: the clearest piece of land, placed first so the place names
# avoid it. KiCad's bold stroke font measures ~0.95 of size per character.
TITLE = "MONTRÉAL"
best = None
gx = 0.5
while gx < G.W_KM:
    gy = 0.5
    while gy < G.H_KM:
        tb = text_box(gx, gy, TITLE, TITLE_MM, char_w=0.95)
        if (land.contains(tb.buffer(0.3)) and tb.distance(G.FRAME.boundary) >= 0.8
                and not any(tb.intersects(p) for p in placed)):
            score = min(tb.distance(avoid), 4.0) - 0.02 * abs(gx - G.W_KM / 2)
            if best is None or score > best[0]:
                best = (score, gx, gy, tb)
        gy += 0.25
    gx += 0.25
assert best, "no land for the wordmark"
title_box = best[3]
tx, ty = c(best[1], best[2])
placed.append(title_box.buffer(0.4))
annotations.append({"text": TITLE, "x": tx, "y": ty,
                    "size": TITLE_MM, "angle": 0, "anchor": "center",
                    "copper": True, "bold": True})


for text, lat, lon in PLACES:
    sx, sy = G.km(lat, lon)
    best = None
    for _ in range(600):
        x, y = sx + random.uniform(-SEED_KM, SEED_KM), sy + random.uniform(-SEED_KM, SEED_KM)
        tb = text_box(x, y, text, CITY_TEXT_MM)
        if (not land.contains(tb) or any(tb.intersects(p) for p in placed)
                or tb.distance(G.FRAME.boundary) < 0.5):
            continue
        score = min(tb.distance(avoid), 1.5) - 0.1 * math.hypot(x - sx, y - sy)
        if best is None or score > best[0]:
            best = (score, x, y, tb)
    if best is None or best[3].distance(avoid) < 0.15:
        print(f"  no spot for {text}")
        continue
    placed.append(best[3].buffer(0.3))
    x, y = c(best[1], best[2])
    annotations.append({"text": text, "x": x, "y": y, "size": CITY_TEXT_MM,
                        "angle": 0, "anchor": "center", "copper": True})
print(f"city labels: {len(annotations)}")

d["geo"] = geo
d["annotations"] = annotations
d["canvas_mm"] = CANVAS_W
d["canvas_h_mm"] = CANVAS_H
d["board_scale"] = BOARD
json.dump(d, open("montreal.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"wrote montreal.json: board {CANVAS_W * BOARD:.0f} x {CANVAS_H * BOARD:.1f} mm, "
      f"{MM_PER_KM:.2f} mm/km, {len(geo)} geo, {len(annotations)} annotations")
