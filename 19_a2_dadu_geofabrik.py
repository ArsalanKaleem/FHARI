"""Decision 7: Dadu rerouted on the Geofabrik Pakistan OSM extract of 2026-07-12.

Source: Geofabrik Pakistan extract of 2026-07-12, gis_osm_roads_free_1.shp, path given by env GEOFABRIK_ROADS (read only).
NOTE: the extract postdates the 2022 flood by ~4 years; roads mapped (or built) after 2022 are
included, so this is a completeness check of the cached RHAI-era graph, not a 2022 network.
Graph build: drive classes (fclass in DRIVE below, approximating OSMnx network_type="drive";
`track` and paths excluded as in OSMnx drive; `service` kept), clipped to the Dadu GADM polygon,
lines noded with shapely.union_all (every crossing becomes a junction — over-/underpasses become
false junctions, which can only add connectivity), largest weakly connected component, RHAI speeds
by class, one-way handling from the Geofabrik `oneway` field (F forward, T reverse, B both).
Then: segment exposure (05 code, v1 masks) and the same normal + flood routing as A2 for Scenario A
and B; compare with the cached-graph results for Dadu at the base config (2022, D3, T0.6) under the
r = 0 rule and the decision-6 rule (isolated = no reachable node within 1 km).
Writes results/tables/a2_dadu_geofabrik_compare.csv and data/a2_dadu_geofabrik.parquet.
"""
import os

import networkx as nx
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy.spatial import cKDTree

from _common import DATA, TABLES, PAPER, VID, log_env, set_seeds
import _routing as R

set_seeds()
log_env(__file__)
SHP = os.environ.get("GEOFABRIK_ROADS")   # path to Geofabrik Pakistan gis_osm_roads_free_1.shp
if not SHP:
    raise SystemExit("set GEOFABRIK_ROADS to the Geofabrik Pakistan roads shapefile (gis_osm_roads_free_1.shp)")
DRIVE = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
         "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
         "service", "road"}
SPEED = {"motorway": 90, "trunk": 70, "primary": 55, "secondary": 45, "tertiary": 35, "unclassified": 25,
         "residential": 20, "track": 15, "path": 8, "service": 20}
EV, D, T = "2022", 3, 0.6

src = (PAPER / "05_a1_segment_exposure.py").read_text(encoding="utf-8").split("ap = argparse.ArgumentParser()")[0]
expo_mod = {"__file__": str(PAPER / "05_a1_segment_exposure.py"), "__name__": "expo"}
exec(compile(src, "05_a1_segment_exposure.py", "exec"), expo_mod)
exposure_for = expo_mod["exposure_for"]

dadu = R.districts().query("district == 'Dadu'")
import sys
SOURCE = sys.argv[1] if len(sys.argv) > 1 else "geofabrik"
if SOURCE == "geofabrik":
    roads = gpd.read_file(SHP, bbox=tuple(dadu.total_bounds), engine="pyogrio")
    roads = roads[roads["fclass"].isin(DRIVE)]
    roads = gpd.clip(roads, dadu.union_all())
    GRAPH_LABEL = "geofabrik_2026-07-12"
else:   # construction-artefact test: cached OSMnx edges pushed through the same build
    ce = gpd.read_parquet(PAPER / "cache/graphs/Dadu__overpass.kumi.systems__edges.parquet")
    ce = ce.drop_duplicates(subset=["osmid", "length"])          # one line per two-way road
    roads = gpd.GeoDataFrame({"fclass": ce["highway"].astype(str).str.strip("[]'").str.split("'").str[0],
                              "oneway": np.where(ce["oneway"].astype(bool), "F", "B"), "osm_id": ce["osmid"]},
                             geometry=ce.geometry, crs=4326)
    GRAPH_LABEL = "cached_edges_rebuilt"
roads = roads.explode(index_parts=False).to_crs(32642)
print(f"{GRAPH_LABEL} drive lines in Dadu: {len(roads):,}")

# node at every crossing, keep fclass/oneway by carrying attributes via spatial join on midpoints
noded = shapely.union_all(roads.geometry.to_numpy())
segs = gpd.GeoDataFrame(geometry=list(shapely.get_parts(noded)), crs=32642)
segs = segs[segs.geometry.length > 0.5]
mid = gpd.GeoDataFrame(geometry=segs.geometry.interpolate(0.5, normalized=True), crs=32642)
j = gpd.sjoin_nearest(mid, roads[["fclass", "oneway", "osm_id", "geometry"]], how="left", max_distance=1.0)
j = j[~j.index.duplicated(keep="first")]
segs = segs.join(j[["fclass", "oneway", "osm_id"]])
segs["highway"] = segs["fclass"].str.replace("_link", "", regex=False).replace({"living_street": "residential", "road": "unclassified"})
segs["speed_kph"] = segs["highway"].map(SPEED).fillna(25)
segs["length"] = segs.geometry.length
segs["travel_time"] = segs["length"] / (segs["speed_kph"] * 1000 / 3600)

G = nx.MultiDiGraph(crs="epsg:4326", simplified=False)
xy = {}
segs4326 = segs.to_crs(4326)


def nid(pt):
    k = (round(pt[0], 7), round(pt[1], 7))
    if k not in xy:
        xy[k] = len(xy)
        G.add_node(xy[k], x=k[0], y=k[1])
    return xy[k]


# OSMnx-style: one edge per consecutive vertex pair, then ox.simplify_graph merges degree-2 chains
# into junction-to-junction edges (lengths/times summed), as OSMnx does for OSM ways.
import osmnx as ox
for (g, g4), r in zip(zip(segs.geometry, segs4326.geometry), segs.itertuples(index=False)):
    cm, cg = list(g.coords), list(g4.coords)
    ow = str(r.oneway)
    for (p0, p1), (q0, q1) in zip(zip(cm[:-1], cm[1:]), zip(cg[:-1], cg[1:])):
        L = float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        if L == 0:
            continue
        a, b = nid(q0), nid(q1)
        attrs = dict(highway=r.highway, length=L, speed_kph=r.speed_kph, osmid=r.osm_id,
                     travel_time=L / (r.speed_kph * 1000 / 3600), oneway=ow in ("F", "T"), reversed=False)
        if ow in ("F", "B", "None", "nan", ""):
            G.add_edge(a, b, **attrs)
        if ow in ("T", "B", "None", "nan", ""):
            G.add_edge(b, a, **attrs)
G = ox.simplify_graph(G, edge_attrs_differ=["highway"],
                      edge_attr_aggs={"length": sum, "travel_time": sum})
largest = max(nx.weakly_connected_components(G), key=len)
G = G.subgraph(largest).copy()
print(f"{GRAPH_LABEL} graph: nodes {G.number_of_nodes():,}, edges {G.number_of_edges():,}")

# exposure on the new edges
edges = ox.graph_to_gdfs(G, nodes=False, fill_edge_geometry=True).reset_index()[
    ["u", "v", "key", "highway", "length", "travel_time", "geometry"]].to_crs(32642)
ex = exposure_for(edges.reset_index(drop=True), EV)
edges = pd.concat([edges.reset_index(drop=True), ex], axis=1)
closed = set(map(tuple, edges.loc[edges[f"y{EV}_frac_fd_ge{D}"].fillna(0) >= T, ["u", "v", "key"]]
                 .itertuples(index=False, name=None)))
H = G.copy(); H.remove_edges_from(closed)

ng = pd.DataFrame({n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}, index=["x", "y"]).T
ngp = gpd.GeoSeries(gpd.points_from_xy(ng.x, ng.y), crs=4326).to_crs(32642)
tree = cKDTree(np.c_[ngp.x, ngp.y]); ids = ng.index.to_numpy()
rows = []
for s in ("A", "B"):
    v, f = R.district_inputs("Dadu", R.load_facilities(s))
    v, f = R.snap(G, v, f)
    vxy = v.to_crs(32642); vxy = np.c_[vxy.geometry.x, vxy.geometry.y]
    src_n = [n for n in pd.unique(f["node"]) if n in G]
    norm = nx.multi_source_dijkstra_path_length(G, src_n, weight="travel_time")
    flood = nx.multi_source_dijkstra_path_length(H, src_n, weight="travel_time")
    near1k = tree.query_ball_point(vxy, 1000)
    for i, (vid, n) in enumerate(zip(v[VID], v["node"])):
        t1 = [flood[ids[j]] for j in near1k[i] if ids[j] in flood]
        rows.append({VID: vid, "scenario": s, "graph": GRAPH_LABEL,
                     "normal_min": norm.get(n, np.nan) / 60, "flood_min_r0": flood.get(n, np.nan) / 60,
                     "flood_min_r1km": min(t1) / 60 if t1 else np.nan,
                     "no_road_1km": len(near1k[i]) == 0})
geo = pd.DataFrame(rows)
geo.to_parquet(DATA / f"a2_dadu_{SOURCE}.parquet", index=False)

# cached-graph comparison (r0 from A2; r1km recomputed the same way on the cached graph)
cached = pd.read_parquet(DATA / "a2_flood/Dadu.parquet")
cached = cached[(cached.event == EV) & (cached.D == D) & (cached["T"] == T)][[VID, "scenario", "min_any"]]
nt = pd.read_parquet(DATA / "a2_normal_times.parquet")
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "population", "pop_part2km"])
Gc = R.load_graph("Dadu", "overpass.kumi.systems")
ec = pd.read_parquet(DATA / "segment_exposure/Dadu__overpass.kumi.systems.parquet")
ecg = pd.read_parquet(PAPER / "cache/graphs/Dadu__overpass.kumi.systems__edges.parquet")
br = ecg["bridge"].astype(str).str.contains("yes", case=False, na=False) if "bridge" in ecg else pd.Series(False, index=ecg.index)
ec = ec.merge(ecg[["u", "v", "key"]].assign(bridge=br.to_numpy()), on=["u", "v", "key"])
cl = set(map(tuple, ec.loc[(ec[f"y{EV}_frac_fd_ge{D}"].fillna(0) >= T) & ~ec.bridge, ["u", "v", "key"]].itertuples(index=False, name=None)))
Hc = Gc.copy(); Hc.remove_edges_from(cl)
ngc = pd.DataFrame({n: (d["x"], d["y"]) for n, d in Gc.nodes(data=True)}, index=["x", "y"]).T
ngcp = gpd.GeoSeries(gpd.points_from_xy(ngc.x, ngc.y), crs=4326).to_crs(32642)
treec = cKDTree(np.c_[ngcp.x, ngcp.y]); idsc = ngc.index.to_numpy()
crow = []
for s in ("A", "B"):
    v, f = R.district_inputs("Dadu", R.load_facilities(s))
    v, f = R.snap(Gc, v, f)
    vxy = v.to_crs(32642); vxy = np.c_[vxy.geometry.x, vxy.geometry.y]
    fl = nx.multi_source_dijkstra_path_length(Hc, [n for n in pd.unique(f["node"]) if n in Hc], weight="travel_time")
    nb = treec.query_ball_point(vxy, 1000)
    for i, vid in enumerate(v[VID]):
        t1 = [fl[idsc[j]] for j in nb[i] if idsc[j] in fl]
        crow.append({VID: vid, "scenario": s, "flood_min_r1km": min(t1) / 60 if t1 else np.nan,
                     "no_road_1km": len(nb[i]) == 0})
cach = pd.DataFrame(crow).merge(cached.rename(columns={"min_any": "flood_min_r0"}), on=[VID, "scenario"])
cach = cach.merge(nt[[VID, "min_any_A", "min_any_B"]], on=VID)
cach["normal_min"] = np.where(cach.scenario == "A", cach.min_any_A, cach.min_any_B)
cach["graph"] = "cached_rhai"

both = pd.concat([cach[geo.columns], geo]).merge(pop, on=VID)
out = []
for (g, s), d in both.groupby(["graph", "scenario"]):
    road = ~d.no_road_1km
    out.append({"graph": g, "scenario": s, "villages": len(d), "closed_edges": len(cl) if g == "cached_rhai" else len(closed),
                "normal_median_min_unweighted": float(np.nanmedian(d.normal_min)),
                "no_mapped_road_1km_villages": int(d.no_road_1km.sum()),
                "isolated_r0_villages": int(d.flood_min_r0.isna().sum()),
                "isolated_r0_people_dedup": float(d.loc[d.flood_min_r0.isna(), "pop_part2km"].sum()),
                "isolated_r1km_villages": int((d.flood_min_r1km.isna() & road).sum()),
                "isolated_r1km_people_dedup": float(d.loc[d.flood_min_r1km.isna() & road, "pop_part2km"].sum())})
cmp = pd.DataFrame(out)
cmp.to_csv(TABLES / f"a2_dadu_{SOURCE}_compare.csv", index=False)
pd.set_option("display.width", 220)
print(cmp.round(1).to_string(index=False))
