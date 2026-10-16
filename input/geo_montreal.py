"""Greater Montreal land / water from OpenStreetMap water POLYGONS.

Why this source: the island sits in fresh water (the St. Lawrence, Riviere
des Prairies, Riviere des Mille Iles, Lac Saint-Louis, Lac des
Deux-Montagnes), so there is no sea and no coastline to trace - every piece
of water is already a `natural=water` polygon in OSM (ways and multipolygon
relations). Nothing is assembled from coastline lines and nothing has to
decide inside from outside; relation rings are stitched with polygonize and
that is all. land = frame - water.

Fetched once with Overpass and cached in osm/water.json (see FETCH at the
bottom). Coordinates are projected with a local equirectangular projection
into km from the frame's north-west corner, y down. `water()` returns the
smoothed water geometry in that frame; `python geo_montreal.py` renders a
preview PNG with the stations overlaid.
"""
import json
import math
import os

from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import polygonize, unary_union

# --- frame ------------------------------------------------------------------
# Metro only (four lines + the Blue line extension), north-up, on a 2:1
# board the same size as Vancouver's: 200 x 100 mm.
#
# The map is deliberately NOT to scale. The network is nearly square and
# its downtown stations sit 400-500 m apart, so a true-scale 2:1 frame puts
# them under the LED pitch floor with half the board blank. Instead every
# coordinate goes through a separable warp (see km()):
#   * the whole map is stretched east-west by STRETCH_X
#   * a smooth bump magnifies downtown, by up to 1 + BUMP_X east-west and
#     1 + BUMP_Y north-south at the centre, fading over BUMP_*_KM
# Land and water go through the same warp as the stations, so everything
# stays on the right side of every shoreline. Being separable and monotone,
# the warp cannot fold, and the lat/lon frame stays a rectangle.
#
# The frame is set by its north, south and EAST edges; the west edge falls
# wherever the 2:1 aspect puts it, so blank South Shore is traded for room
# on the West Island side (where the wordmark sits).
LAT0, LAT1 = 45.612, 45.436          # north .. south
LON1 = -73.478                       # east edge, just past Longueuil's label
BOARD_W_MM = 200.0
ASPECT = 2.0                         # board width / height
CENTRE = (45.506, -73.570)           # downtown: between McGill and Place-des-Arts
STRETCH_X = 1.15
BUMP_X, BUMP_X_KM = 1.6, 3.5
BUMP_Y, BUMP_Y_KM = 0.6, 3.0
LAT_MID = (LAT0 + LAT1) / 2
KX, KY = 111.32 * math.cos(math.radians(LAT_MID)), 111.32   # km per degree


def _bump(t, amp, width):
    """Integral of 1 + amp * exp(-(t/width)^2): identity far from 0,
    magnified by 1 + amp at 0."""
    return t + amp * width * math.sqrt(math.pi) / 2 * math.erf(t / width)


def _wx(lon):
    return STRETCH_X * _bump((lon - CENTRE[1]) * KX, BUMP_X, BUMP_X_KM)


def _wy(lat):
    return _bump((CENTRE[0] - lat) * KY, BUMP_Y, BUMP_Y_KM)


# Frame in warped km ("board km": mm = km * BOARD_W_MM / W_KM everywhere)
H_KM = _wy(LAT1) - _wy(LAT0)
W_KM = ASPECT * H_KM
_X0, _Y0 = _wx(LON1) - W_KM, _wy(LAT0)
FRAME = box(0, 0, W_KM, H_KM)
FRAME_NAME = "metro"


def km(lat, lon):
    """Frame-relative warped km: x east from the west edge, y south from
    the north edge."""
    return (_wx(lon) - _X0, _wy(lat) - _Y0)


def _densify(ring, step=0.004):
    """Insert points so no lon/lat step exceeds `step` degrees (~300 m): the
    warp is nonlinear, so a long straight shoreline must bend with it."""
    out = [ring[0]]
    for a, b in zip(ring, ring[1:]):
        n = int(max(abs(b["lat"] - a["lat"]), abs(b["lon"] - a["lon"])) / step)
        for i in range(1, n + 1):
            t = i / (n + 1)
            out.append({"lat": a["lat"] + (b["lat"] - a["lat"]) * t,
                        "lon": a["lon"] + (b["lon"] - a["lon"]) * t})
        out.append(b)
    return out


def _ring(geometry):
    return [km(p["lat"], p["lon"]) for p in _densify(geometry)]


def _polygon(el):
    """One OSM element (closed way, or multipolygon relation with member
    geometry) -> shapely polygon in frame km, or None."""
    if el["type"] == "way":
        r = _ring(el["geometry"])
        return Polygon(r).buffer(0) if len(r) >= 4 and r[0] == r[-1] else None
    ways = [m for m in el["members"] if m["type"] == "way" and "geometry" in m]
    outer = [LineString(_ring(m["geometry"])) for m in ways if m["role"] != "inner"]
    inner = [LineString(_ring(m["geometry"])) for m in ways if m["role"] == "inner"]
    if not outer:
        return None
    g = unary_union(list(polygonize(unary_union(outer))))
    if inner:
        g = g.difference(unary_union(list(polygonize(unary_union(inner)))))
    return g.buffer(0)


def _elements():
    return json.load(open("osm/water.json", encoding="utf-8"))["elements"]


# Flowing / navigable water: kept when wide enough. Everything else
# (water=pond/basin/reservoir/untagged) is dropped unless whitelisted.
FLOW_KINDS = {"river", "rapids", "canal", "harbour", "lake"}
MIN_FLOW_KM2 = 0.3          # a river/lake polygon smaller than this is a creek or pond
MIN_RIVER_WIDTH_KM = 0.10   # mean width (2*area/perimeter); drops creeks and the Lachine Canal
# Lakes worth showing that are not part of the river system - by name, so a
# quarry pond doesn't sneak in on area alone. Empty until one is asked for.
KEEP_LAKES = set()
# River islands smaller than this are filled; Ile Sainte-Helene, Ile
# Notre-Dame, Ile des Soeurs, Ile Bizard, Ile Perrot, Ile Bigras survive.
MIN_ISLAND_KM2 = 0.25
SMOOTH_KM = 0.05          # simplify tolerance
OPEN_CLOSE_KM = 0.035     # drops nooks narrower than ~70 m
MIN_PIECE_KM2 = 0.5       # a connected water piece must be at least this


def flow_raw():
    out = []
    for el in _elements():
        t = el.get("tags", {})
        if t.get("water") not in FLOW_KINDS:
            continue
        g = _polygon(el)
        if g is None or g.is_empty or g.area < MIN_FLOW_KM2:
            continue
        if 2 * g.area / g.length >= MIN_RIVER_WIDTH_KM:
            out.append(g)
    return unary_union(out)


def lakes_raw():
    out = [_polygon(el) for el in _elements()
           if el.get("tags", {}).get("name") in KEEP_LAKES]
    return unary_union([g for g in out if g is not None])


def _fill_small_holes(geom, min_km2):
    out = []
    for g in getattr(geom, "geoms", [geom]):
        out.append(Polygon(g.exterior, [r for r in g.interiors
                                        if Polygon(r).area >= min_km2]))
    return unary_union(out)


def water(smooth=True):
    flow = flow_raw().intersection(FRAME)
    # keep the big connected water; drop slivers that only clip a frame edge
    flow = unary_union([g for g in getattr(flow, "geoms", [flow])
                        if g.area >= MIN_PIECE_KM2 and
                        not (g.area < 3.0 and g.intersects(FRAME.boundary))])
    w = unary_union([flow, lakes_raw().intersection(FRAME)])
    if smooth:
        w = w.buffer(-OPEN_CLOSE_KM).buffer(2 * OPEN_CLOSE_KM).buffer(-OPEN_CLOSE_KM)
        w = w.simplify(SMOOTH_KM, preserve_topology=True)
        w = _fill_small_holes(w, MIN_ISLAND_KM2)
        w = unary_union([g for g in getattr(w, "geoms", [w]) if g.area >= 0.05])
        w = w.intersection(FRAME)
    return w


def render(path, water_geom, stations=None, lines=None, dpi=110):
    """Preview PNG: board colours, frame = board aspect, stations overlaid."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(15, 15 * H_KM / W_KM), dpi=dpi)
    ax.set_facecolor("#2f5442")
    for g in getattr(water_geom, "geoms", [water_geom]):
        x, y = g.exterior.xy
        ax.fill(x, y, color="#f2d43a", lw=0)
        for r in g.interiors:
            x, y = r.xy
            ax.fill(x, y, color="#2f5442", lw=0)
    for color, path_ids in lines or []:
        pts = [stations[s][:2] for s in path_ids if s in stations]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, lw=1.6, zorder=2)
    for sid, (x, y, name) in (stations or {}).items():
        ax.plot(x, y, "o", ms=4, mfc="white", mec="black", mew=0.5, zorder=3)
        ax.text(x + 0.15, y - 0.15, name, fontsize=5, color="white", zorder=4)
    ax.set_xlim(0, W_KM)
    ax.set_ylim(H_KM, 0)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    plt.subplots_adjust(0, 0, 1, 1)
    plt.savefig(path, dpi=dpi)
    plt.close(fig)


if __name__ == "__main__":
    import sys
    w = water()
    mm_per_km = BOARD_W_MM / W_KM
    print(f"frame '{FRAME_NAME}' {W_KM:.1f} x {H_KM:.1f} km -> board {BOARD_W_MM:.0f} x "
          f"{H_KM * mm_per_km:.1f} mm at {mm_per_km:.2f} mm/km")
    print(f"water: {len(getattr(w, 'geoms', [w]))} piece(s), "
          f"{w.area:.0f} km^2 of {W_KM * H_KM:.0f}")
    stations, lines = {}, []
    try:
        src = "montreal.json" if os.path.exists("montreal.json") else "montreal.skeleton.json"
        d = json.load(open(src, encoding="utf-8"))
        st = json.load(open("montreal_station_latlon.json", encoding="utf-8"))
        for sid, (lat, lon) in st.items():
            x, y = km(lat, lon)
            if FRAME.contains(box(x, y, x, y).centroid):
                stations[sid] = (x, y, d["stations"].get(sid, {}).get("name", sid))
        lines = [(ln["color"], p) for ln in d["lines"] for p in ln["paths"]]
        wet = [s for s, (x, y, _) in stations.items() if w.contains(box(x, y, x, y).centroid)]
        print(f"stations in frame: {len(stations)}; in water: {wet or 'none'}")
    except FileNotFoundError:
        pass
    out = sys.argv[1] if len(sys.argv) > 1 else "../test-results/geo-preview.png"
    render(out, w, stations, lines)
    print("wrote", out)

# FETCH (Overpass bbox south,west,north,east = 45.36,-74.02,45.68,-73.36):
#   curl -s -A "transit-pcb/1.0" --max-time 300 https://overpass-api.de/api/interpreter \
#     --data-urlencode 'data=[out:json][timeout:240];(way["natural"="water"](BBOX);
#       relation["natural"="water"](BBOX););out body geom;' -o osm/water.json
#   Use `out body geom`: `out tags geom` drops relation members, so the big
#   rivers and lakes (all multipolygon relations) cannot be rebuilt.
