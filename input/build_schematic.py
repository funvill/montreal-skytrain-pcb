"""Assemble montreal-schematic.json: the metro drawn the way the official STM
map draws it - straight diagonal runs, even station spacing, rounded bends -
laid over the real land and water, instead of the geographic layout in
montreal.json (the "natural" map).

Same schema, same lines / names / chain (from montreal.skeleton.json), so
every tool in ../tools works on either file.

Lines are hand-authored on a unit grid:

    board mm = (OX + gx * U * XS,  OY + gy * U)

Stations sit on straight legs; bends are grid CORNERS between stations and
are rounded off (BEND_MM), written to each line's "shape" so the checker,
the preview and the exporter all draw the same curve. The one bend that
falls on a station (the orange line at Lionel-Groulx) stays sharp - it is
under the interchange ring.

The water is the real thing (geo_montreal's OSM polygons, projected at true
scale) and is NOT stretched to fit the lines: it is placed by the single
rotation + uniform scale + shift that best matches where the stations really
are to where they are drawn here, so the island and the rivers keep their
real proportions. A schematic cannot agree with a true map everywhere, so
LAND_FOLLOW optionally lets the land give a little near the stations
(0 = rigid true-shape land; 1 = land bent until every station sits where it
really is relative to the shore, which is what makes it look stretched).

Labels and suppressed_art already in the output are preserved.

Run:  python build_station_latlon.py && python build_schematic.py [wide|square]
      (then ../tools/auto_label.py ../input/montreal-schematic[-square].json)
"""
import json
import math
import os
import sys

import numpy as np
import shapely
from scipy.interpolate import RBFInterpolator
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import geo_montreal as GEO

# Two boards from the same grid:
#   wide    200 x 100 mm, the 2:1 board; stretched sideways to fill it, so
#           the diagonals sit at about 34 degrees
#   square  160 x 160 mm, 1:1; true 45-degree diagonals
VARIANTS = {
    #          output file                        W      H      U    XS   OX     OY
    "wide":   ("montreal-schematic.json",        200.0, 100.0, 2.9, 1.5, 127.8, 42.7),
    "square": ("montreal-schematic-square.json", 160.0, 160.0, 4.2, 1.0, 87.4, 69.6),
}
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "wide"
# U = grid step, mm; XS = sideways stretch; (OX, OY) = board mm of grid (0, 0) = Berri-UQAM
OUT, BOARD_W, BOARD_H, U, XS, OX, OY = VARIANTS[VARIANT]
BOARD = 2.0                    # board mm per canvas unit
BEND_MM = 4.0                  # bend radius
MIN_PITCH_MM = 3.3
PAD_CLEAR_MM = 2.2
ESCAPE_CLEAR_MM = 3.4          # clearing around a station that touches water (room for vias)
HOLE_INSET_MM = 4.0            # M3 mounting holes, centre to board edge
HOLE_CLEAR_MM = 4.5            # copper art keeps this far from a hole centre
TITLE_MM = 8.0
# The downtown orange line's labels can only go on the river side (the green
# line is on the other), and white silk on bare copper reads poorly. So the
# water near these stations is pushed away from them - by SHORE_PUSH_MM at
# the line, fading to nothing over about twice SHORE_PUSH_FADE_MM. It is a
# push, not a cut: the shoreline keeps its real shape, Old Port piers
# included, and only its distance from the stations is exaggerated.
SHORE_PUSH_STATIONS = ["champ-de-mars", "lucien-l-allier"]     # ends of the run
SHORE_PUSH_MM = float(os.environ.get("SHORE_PUSH_MM", 0.0))   # 0 = true distance
SHORE_PUSH_FADE_MM = 18.0      # must stay above 0.86 * SHORE_PUSH_MM or the water folds
# Water detail (see detailed_raw). Areas are in natural-map km^2.
WATER_FLOW = {"river", "canal", "rapids", "harbour", "lake", "lock", "stream"}
WATER_SKIP = {"wastewater", "reservoir"}
MIN_FLOW_KM2 = 0.01            # rivers / canals / lakes: anything this size or larger
MIN_NAMED_KM2 = 0.03           # other water (park ponds, basins) only if named
MIN_WATER_MM = 0.5             # thinnest copper feature: canals are fattened to this
MIN_PIECE_MM2 = 1.2            # smallest separate piece of water kept
MIN_ISLAND_MM2 = 0.8           # smallest island kept
SHORE_STATIONS = {"cartier", "henri-bourassa", "montmorency", "champ-de-mars", "angrignon"}
# placed to suit the land (see the yellow line), so they must not steer it
FIT_IGNORE = {"jean-drapeau", "longueuil-universite-de-sherbrooke"}
SHORE_WEIGHT = float(os.environ.get("SHORE_WEIGHT", 6.0))
LAND_FOLLOW = float(os.environ.get("LAND_FOLLOW", 0.0))
LAND_FOLLOW_KM = 4.0           # how local the give is: reach of each station's pull


def run(start, step, ids):
    """Stations after `start`, one `step` apart."""
    return {sid: (start[0] + step[0] * (i + 1), start[1] + step[1] * (i + 1))
            for i, sid in enumerate(ids)}


G = {"berri-uqam": (0, 0), "lionel-groulx": (-7, 9.5), "snowdon": (-11, 5.5),
     "jean-talon": (-6, -6)}
CORNERS = {}                   # "a|b" -> grid corner(s) on the way from a to b

# Green: one straight diagonal from Atwater through Berri-UQAM to
# Honoré-Beaugrand; a short vertical leg through Lionel-Groulx; down-left.
G.update(run(G["berri-uqam"], (-1, 1),
             ["saint-laurent", "place-des-arts", "mcgill", "peel", "guy-concordia", "atwater"]))
G.update(run(G["berri-uqam"], (1, -1),
             ["beaudry", "papineau", "frontenac", "prefontaine", "joliette", "pie-ix",
              "viau", "assomption", "cadillac", "langelier", "radisson", "honore-beaugrand"]))
CORNERS["atwater|lionel-groulx"] = [(-7, 7)]
CORNERS["lionel-groulx|charlevoix"] = [(-7, 11)]
G.update(run((-7, 11), (-1, 1),
             ["charlevoix", "lasalle", "de-l-eglise", "verdun", "jolicoeur", "monk", "angrignon"]))
# Orange: a U. West arm up-left from Lionel-Groulx; the downtown diagonal
# beside the green line; round the bend to Berri-UQAM; up-left; west to Laval.
G.update(run(G["lionel-groulx"], (-1, -1), ["place-saint-henri", "vendome", "villa-maria"]))
G.update(run(G["snowdon"], (-1, -1),
             ["cote-sainte-catherine", "plamondon", "namur", "de-la-savane", "du-college",
              "cote-vertu"]))
G.update(run(G["lionel-groulx"], (1, -1),
             ["georges-vanier", "lucien-l-allier", "bonaventure", "square-victoria-oaci",
              "place-d-armes", "champ-de-mars"]))
CORNERS["champ-de-mars|berri-uqam"] = [(1.25, 1.25)]
G.update(run(G["berri-uqam"], (-1, -1),
             ["sherbrooke", "mont-royal", "laurier", "rosemont", "beaubien"]))
G.update(run(G["jean-talon"], (-1, -1), ["jarry", "cremazie", "sauve", "henri-bourassa"]))
G["cartier"] = (-12, -12)                      # a double step: the river runs between
CORNERS["cartier|de-la-concorde"] = [(-13, -13)]
G.update(run((-13, -13), (-1.5, 0), ["de-la-concorde", "montmorency"]))
# Blue: up-right from Snowdon, a vertical run, up-right through Jean-Talon,
# then the extension east along a level run.
G.update(run(G["snowdon"], (1, -1), ["cote-des-neiges", "universite-de-montreal"]))
CORNERS["universite-de-montreal|edouard-montpetit"] = [(-8, 2.5)]
G.update(run((-8, 2.7), (0, -1.3), ["edouard-montpetit", "outremont", "acadie", "parc"]))
CORNERS["parc|de-castelnau"] = [(-8, -4)]
G["de-castelnau"] = (-7, -5)
G.update(run(G["jean-talon"], (1, -1), ["fabre", "d-iberville", "saint-michel"]))
CORNERS["saint-michel|vertieres"] = [(-2, -10)]
G.update(run((-2, -10), (1.6, 0),
             ["vertieres", "mary-two-axe-earley", "cesira-parisotto", "madeleine-parent",
              "anjou"]))
# Yellow: east from Berri-UQAM, south across the channel and along the
# island (Jean-Drapeau), then east again to the South Shore. Placed to agree
# with the land, which is not bent to fit: see the header.
CORNERS["berri-uqam|jean-drapeau"] = [(3.2, 0)]
G["jean-drapeau"] = (3.2, 4.6)
CORNERS["jean-drapeau|longueuil-universite-de-sherbrooke"] = [(3.2, 5.6)]
G["longueuil-universite-de-sherbrooke"] = (6.0, 5.6)


def mm(g):
    return (OX + g[0] * U * XS, OY + g[1] * U)


def mm_fit(g):
    return (OX + g[0] * U, OY + g[1] * U)


sk = json.load(open("montreal.skeleton.json", encoding="utf-8"))
d = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
old = d.get("stations", {})
assert set(G) == set(sk["stations"]), (set(G) ^ set(sk["stations"]))
MM = {sid: mm(g) for sid, g in G.items()}
ids = list(MM)
for i, a in enumerate(ids):
    for b in ids[i + 1:]:
        dist = Point(MM[a]).distance(Point(MM[b]))
        assert dist >= MIN_PITCH_MM, f"{a} / {b} only {dist:.2f} mm apart"

# --- rounded bends -----------------------------------------------------------


def fillet(a, p, b, radius, steps=8):
    """Points of the rounded bend at p on the way a -> p -> b (board mm)."""
    ua = ((a[0] - p[0]), (a[1] - p[1]))
    ub = ((b[0] - p[0]), (b[1] - p[1]))
    la, lb = math.hypot(*ua), math.hypot(*ub)
    ua, ub = (ua[0] / la, ua[1] / la), (ub[0] / lb, ub[1] / lb)
    turn = math.pi - math.acos(max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1])))
    t = min(radius * math.tan(turn / 2), 0.8 * la, 0.8 * lb)
    t1 = (p[0] + ua[0] * t, p[1] + ua[1] * t)
    t2 = (p[0] + ub[0] * t, p[1] + ub[1] * t)
    out = []
    for i in range(steps + 1):                  # quadratic Bezier t1 - p - t2
        s = i / steps
        out.append(((1 - s) ** 2 * t1[0] + 2 * s * (1 - s) * p[0] + s ** 2 * t2[0],
                    (1 - s) ** 2 * t1[1] + 2 * s * (1 - s) * p[1] + s ** 2 * t2[1]))
    return out


lines, route_geoms = [], []
used = set()
for line in sk["lines"]:
    shape = {}
    for path in line["paths"]:
        for a, b in zip(path, path[1:]):
            key = f"{a}|{b}" if f"{a}|{b}" in CORNERS else f"{b}|{a}"
            corners = CORNERS.get(key, [])
            if corners and key.startswith(b + "|"):
                corners = corners[::-1]
            used.add(key)
            pts = [MM[a]] + [mm(c) for c in corners] + [MM[b]]
            via = []
            for i in range(1, len(pts) - 1):
                via += fillet(pts[i - 1], pts[i], pts[i + 1], BEND_MM)
            if via:
                shape[f"{a}|{b}"] = [[round(x / BOARD, 3), round(y / BOARD, 3)] for x, y in via]
            route_geoms.append(LineString([MM[a]] + via + [MM[b]]))
    lines.append({**line, **({"shape": shape} if shape else {})})
assert set(CORNERS) <= used, f"corner on no line: {set(CORNERS) - used}"
routes = unary_union(route_geoms)

d.update(city="montreal", lines=lines, extras=sk["extras"], chain=sk["chain"])
d["stations"] = {}
for sid, st in sk["stations"].items():
    d["stations"][sid] = {**st, "x": round(MM[sid][0] / BOARD, 2), "y": round(MM[sid][1] / BOARD, 2),
                          **{k: v for k, v in old.get(sid, {}).items() if k == "label"}}

# --- real water, warped onto the schematic ----------------------------------
FRAME = box(0, 0, BOARD_W, BOARD_H)
LL = json.load(open("montreal_station_latlon.json", encoding="utf-8"))
# true-scale projection: switch off the natural map's downtown magnification
GEO.STRETCH_X, GEO.BUMP_X, GEO.BUMP_Y = 1.0, 0.0, 0.0
src = np.array([GEO.km(*LL[sid]) for sid in ids])
dst = np.array([MM[sid] for sid in ids])
# fit in the unstretched layout (XS = 1) so the land keeps its proportions on
# the square board; the wide board then stretches land and lines alike
dst_fit = np.array([mm_fit(G[sid]) for sid in ids])

# best-fit similarity (rotation + uniform scale + shift, no mirror), km -> mm
# weighted: the stations whose side of the water matters count for more
_w = np.array([0.0 if sid in FIT_IGNORE else SHORE_WEIGHT if sid in SHORE_STATIONS else 1.0
               for sid in ids])[:, None]
_sc, _dc = (src * _w).sum(axis=0) / _w.sum(), (dst_fit * _w).sum(axis=0) / _w.sum()
_u, _sv, _vt = np.linalg.svd(((dst_fit - _dc) * _w).T @ (src - _sc))
_flip = np.diag([1.0, np.sign(np.linalg.det(_u @ _vt))])
ROT = _u @ _flip @ _vt
MM_PER_KM = float((_sv * np.diag(_flip)).sum() / (_w * (src - _sc) ** 2).sum())


def similar(xy):
    out = (xy - _sc) @ ROT.T * MM_PER_KM + _dc
    out[:, 0] = OX + (out[:, 0] - OX) * XS
    return out


# what the rigid placement leaves over at each station, as a smooth local
# field that fades to nothing away from the network
_resid = RBFInterpolator(src, dst - similar(src), kernel="gaussian",
                         epsilon=1.0 / LAND_FOLLOW_KM, smoothing=1.0, degree=-1)


def warp(xy):
    return similar(xy) + (LAND_FOLLOW * _resid(xy) if LAND_FOLLOW else 0.0)


print(f"land: {MM_PER_KM:.2f} mm/km, rotated "
      f"{math.degrees(math.atan2(ROT[1, 0], ROT[0, 0])):.0f} deg, follow {LAND_FOLLOW}")



def detailed_raw():
    """Every piece of water worth drawing at this scale, in natural-map km.

    The natural map keeps only the wide rivers (geo_montreal.flow_raw); the
    schematic has room for more, so this also takes the canals (Lachine, the
    Seaway along the South Shore), the narrow river channels and the small
    rivers, plus the named lakes and basins in the parks. Sewage works and
    reservoirs are left out."""
    out = []
    for el in GEO._elements():
        t = el.get("tags", {})
        kind = t.get("water")
        if kind in WATER_SKIP:
            continue
        g = GEO._polygon(el)
        if g is None or g.is_empty:
            continue
        floor = MIN_FLOW_KM2 if kind in WATER_FLOW else MIN_NAMED_KM2 if t.get("name") else None
        if floor is not None and g.area >= floor:
            out.append(g)
    return unary_union(out)


raw = shapely.segmentize(detailed_raw(), 0.1)              # km; bend long edges with the warp


def push_from_run(xy):
    """Move points radially away from the downtown orange run."""
    a, b = (np.array(MM[sid]) for sid in SHORE_PUSH_STATIONS)
    ab = b - a
    t = np.clip(((xy - a) @ ab) / (ab @ ab), 0.0, 1.0)
    v = xy - (a + t[:, None] * ab)
    r = np.maximum(np.hypot(v[:, 0], v[:, 1]), 1e-9)
    grow = SHORE_PUSH_MM * np.exp(-(r / SHORE_PUSH_FADE_MM) ** 2)
    return xy + v * (grow / r)[:, None]


water = shapely.transform(raw, lambda xy: push_from_run(warp(xy))).buffer(0).intersection(FRAME)
# Keep the detail: no nook-smoothing. Fatten by half the minimum width so a
# canal that warps to a hairline still etches, then drop only the specks.
water = water.buffer(MIN_WATER_MM / 2, join_style=1).intersection(FRAME)
water = water.simplify(0.06, preserve_topology=True)
water = unary_union([g for g in getattr(water, "geoms", [water]) if g.area >= MIN_PIECE_MM2])
water = unary_union([Polygon(g.exterior, [r for r in g.interiors
                                          if Polygon(r).area >= MIN_ISLAND_MM2])
                     for g in getattr(water, "geoms", [water])])
wet = sorted(sid for sid in ids if water.contains(Point(MM[sid])))
# A station at the water's edge gets a wider clearing: its four pads can only
# be reached through vias, and vias cannot sit in the bare-copper water.
shore = sorted(sid for sid in ids if water.distance(Point(MM[sid])) < ESCAPE_CLEAR_MM)
for sid, p in MM.items():
    water = water.difference(Point(p).buffer(ESCAPE_CLEAR_MM if sid in shore else PAD_CLEAR_MM, 16))
# mounting holes, one per corner: their pads are bare copper too
HOLES = [(x, y) for x in (HOLE_INSET_MM, BOARD_W - HOLE_INSET_MM)
         for y in (HOLE_INSET_MM, BOARD_H - HOLE_INSET_MM)]
for p in HOLES:
    water = water.difference(Point(p).buffer(HOLE_CLEAR_MM, 16))
land = FRAME.difference(water)


def ring_with_holes(poly):
    """One outline with each hole (an island) bridged in from the nearest
    outer vertex - the data format has no holes."""
    pts = list(poly.exterior.coords)[:-1]
    for ring in poly.interiors:
        hole = list(ring.coords)[:-1]
        i = min(range(len(pts)), key=lambda k: (pts[k][0] - hole[0][0]) ** 2 +
                (pts[k][1] - hole[0][1]) ** 2)
        pts = pts[:i + 1] + hole + [hole[0]] + [pts[i]] + pts[i + 1:]
    return [[round(x / BOARD, 2), round(y / BOARD, 2)] for x, y in pts]


geo = [{"name": f"water-{i}", "type": "water", "points": ring_with_holes(g)}
       for i, g in enumerate(sorted(getattr(water, "geoms", [water]), key=lambda p: -p.area))
       if g.area >= 1.0]

# --- wordmark: the clearest land for the block -----------------------------
TITLE = ["MONTRÉAL"]
tw, th = len(TITLE[0]) * 0.95 * TITLE_MM, 1.3 * TITLE_MM
pitch = 1.8 * TITLE_MM
span = pitch * (len(TITLE) - 1)
avoid = unary_union([routes.buffer(4.0)] + [Point(p).buffer(9.0) for p in MM.values()])
best = None
for cx in np.arange(tw / 2 + 4, BOARD_W - tw / 2 - 4, 1.0):
    for cy in np.arange(th / 2 + 4, BOARD_H - span - th / 2 - 4, 1.0):
        block = box(cx - tw / 2, cy - th / 2, cx + tw / 2, cy + span + th / 2)
        if not land.contains(block.buffer(1.5)) or block.intersects(avoid):
            continue
        score = min(block.distance(avoid), 12.0) + min(block.distance(water), 6.0)
        if best is None or score > best[0]:
            best = (score, float(cx), float(cy))
annotations = []
if best:
    for i, text in enumerate(TITLE):
        annotations.append({"text": text, "x": round(best[1] / BOARD, 2),
                            "y": round((best[2] + i * pitch) / BOARD, 2), "size": TITLE_MM,
                            "angle": 0, "anchor": "center", "copper": True, "bold": True})
else:
    print("  warning: no clear land for the wordmark")

d["geo"] = geo
d["mounting_holes"] = [list(p) for p in HOLES]
d["annotations"] = annotations
d["canvas_mm"] = BOARD_W / BOARD
d["canvas_h_mm"] = BOARD_H / BOARD
d["board_scale"] = BOARD
json.dump(d, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
xs = [p[0] for p in MM.values()]
ys = [p[1] for p in MM.values()]
print(f"wrote {OUT}: board {BOARD_W:.0f} x {BOARD_H:.0f} mm, {len(MM)} stations spanning "
      f"x {min(xs):.1f}..{max(xs):.1f}, y {min(ys):.1f}..{max(ys):.1f} mm, {len(geo)} water")
print(f"stations whose pad sits in water (island carved): {wet or 'none'}")
print(f"stations given a wider clearing at the shore: {shore or 'none'}")
if os.environ.get("SHOW_TRUE"):
    for sid in os.environ["SHOW_TRUE"].split(","):
        tx, ty = similar(src[[ids.index(sid)]])[0]
        print(f"  {sid}: drawn at grid {G[sid]}, really at grid "
              f"({(tx - OX) / (U * XS):.2f}, {(ty - OY) / U:.2f})")
