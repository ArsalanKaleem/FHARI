"""Pre-A3 check 4: snapping distance, flooded-node vs cut-off isolation, canal / permanent water.

(a) Snapping: straight-line distance (m) from each village point to its snapped graph node.
(b) Isolation sensitivity, base scenario (2022, D3, T0.6, bridges open), A and B: a village is
    "isolated" at radius r if no node within r metres of the village point is reachable from a
    facility on the flooded network. r = 0 reproduces A2 (snapped node only). Each isolated village
    is classed as
       flooded_node  its snapped node lost every incident edge (node submerged)
       cut_off       its snapped node is on a dry fragment that contains no reachable facility
(c) Canals / permanent water: share of base-closed edges lying within 50 m of a mapped canal or
    river line (SWAI canals_utm / rivers_utm) vs the same share among all edges. JRC GSW occurrence
    >= 90 % is the only water mask in A1; narrow canals are mostly below its 30 m resolution.
Writes results/tables/check4_snapping.csv, check4_isolation_radius.csv, check4_canals.csv and
data/check4_spotcheck_candidates.csv (villages for the imagery spot-check).
"""
import networkx as nx
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree
import shapely

from _common import SWAI, DATA, TABLES, VID, SEED, log_env, set_seeds
import _routing as R

set_seeds()
log_env(__file__)
RADII = (0, 250, 500, 1000, 2000)
EV, D, T = "2022", 3, 0.6
nt = pd.read_parquet(DATA / "a2_normal_times.parquet", columns=[VID, "district", "graph"])
pop = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "population"])
fac = {s: R.load_facilities(s) for s in ("A", "B")}
canals = pd.concat([gpd.read_file(SWAI / "data/canals_utm.gpkg").to_crs(32642).geometry,
                    gpd.read_file(SWAI / "data/rivers_utm.gpkg").to_crs(32642).geometry])
canal_tree = shapely.STRtree(canals.to_numpy())

snap_rows, iso_rows, canal_rows = [], [], []
for dname, sub in nt.groupby("district"):
    host = sub["graph"].iloc[0]
    G = R.load_graph(dname, host)
    expo = pd.read_parquet(DATA / f"segment_exposure/{R.safe_name(dname)}__{host}.parquet")
    edges = gpd.read_parquet(DATA.parent / f"cache/graphs/{R.safe_name(dname)}__{host}__edges.parquet")
    if "bridge" not in edges.columns:
        edges["bridge"] = None
    expo = expo.merge(edges[["u", "v", "key", "bridge", "geometry"]], on=["u", "v", "key"])
    is_bridge = expo["bridge"].astype(str).str.contains("yes", case=False, na=False)
    closed_m = (expo[f"y{EV}_frac_fd_ge{D}"].fillna(0) >= T) & ~is_bridge
    closed = set(map(tuple, expo.loc[closed_m, ["u", "v", "key"]].itertuples(index=False, name=None)))
    H = G.copy(); H.remove_edges_from(closed)

    # (c) canal proximity of closed vs all edges (one row per district)
    g = gpd.GeoDataFrame(expo[["u", "v", "key"]], geometry=expo["geometry"], crs=4326).to_crs(32642)
    hit = canal_tree.query(g.geometry.to_numpy(), predicate="dwithin", distance=50.0)
    near = np.zeros(len(g), bool); near[np.unique(hit[0])] = True
    canal_rows.append({"district": dname, "edges": len(g), "closed": int(closed_m.sum()),
                       "share_all_near_water": near.mean(),
                       "share_closed_near_water": near[closed_m.to_numpy()].mean() if closed_m.any() else np.nan})

    nodes = pd.DataFrame({n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}, index=["x", "y"]).T
    ng = gpd.GeoSeries(gpd.points_from_xy(nodes.x, nodes.y), crs=4326).to_crs(32642)
    ntree = cKDTree(np.c_[ng.x, ng.y]); nid = nodes.index.to_numpy()
    for s in ("A", "B"):
        v, f = R.district_inputs(dname, fac[s])
        v, f = R.snap(G, v, f)
        vp = v.to_crs(32642)
        vxy = np.c_[vp.geometry.x, vp.geometry.y]
        sn = ng.iloc[pd.Index(nid).get_indexer(v["node"])]
        sd = np.hypot(vxy[:, 0] - sn.x.to_numpy(), vxy[:, 1] - sn.y.to_numpy())
        if s == "B":
            snap_rows.append(pd.DataFrame({VID: v[VID].to_numpy(), "district": dname, "snap_m": sd}))
        src = [n for n in pd.unique(f["node"]) if n in H]
        reach = nx.multi_source_dijkstra_path_length(H, src, weight="travel_time") if src else {}
        comp = {n: i for i, c in enumerate(nx.weakly_connected_components(H)) for n in c}
        for r in RADII:
            if r == 0:
                ok = np.array([n in reach for n in v["node"]])
            else:
                cand = ntree.query_ball_point(vxy, r)
                ok = np.array([(n in reach) or any(nid[j] in reach for j in c) for n, c in zip(v["node"], cand)])
            for i, (vid, n) in enumerate(zip(v[VID], v["node"])):
                if not ok[i]:
                    kind = "flooded_node" if H.degree(n) == 0 else "cut_off"
                    iso_rows.append({VID: vid, "district": dname, "scenario": s, "radius_m": r,
                                     "kind": kind, "snap_m": sd[i]})
    print(f"{dname:16s} closed={int(closed_m.sum()):,}", flush=True)
    del G, H

snap = pd.concat(snap_rows).merge(pop, on=VID)
iso = pd.DataFrame(iso_rows).merge(pop, on=VID)
alt = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "pop_part2km"])
iso = iso.merge(alt, on=VID)
q = snap["snap_m"].quantile([.5, .75, .9, .95, .99, 1]).rename(lambda x: f"q{int(x*100)}")
snap_sum = pd.concat([q, pd.Series({"share_gt_500m": (snap.snap_m > 500).mean(),
                                    "share_gt_1km": (snap.snap_m > 1000).mean(),
                                    "share_gt_2km": (snap.snap_m > 2000).mean()})])
snap.to_csv(TABLES / "check4_snapping_villages.csv", index=False)
snap_sum.to_frame("value").to_csv(TABLES / "check4_snapping.csv")
isum = iso.groupby(["scenario", "radius_m", "kind"]).agg(villages=(VID, "size"), pop_buffer=("population", "sum"),
                                                        pop_part2km=("pop_part2km", "sum")).reset_index()
isum.to_csv(TABLES / "check4_isolation_radius.csv", index=False)
cn = pd.DataFrame(canal_rows)
tot = pd.Series({"district": "ALL", "edges": cn.edges.sum(), "closed": cn.closed.sum(),
                 "share_all_near_water": np.average(cn.share_all_near_water, weights=cn.edges),
                 "share_closed_near_water": np.average(cn.share_closed_near_water.fillna(0), weights=cn.closed)})
cn = pd.concat([cn, tot.to_frame().T], ignore_index=True)
cn.to_csv(TABLES / "check4_canals.csv", index=False)

# spot-check sample: base-isolated (r=0) villages under B, stratified by kind, plus delayed controls
rng = np.random.default_rng(SEED)
b0 = iso[(iso.scenario == "B") & (iso.radius_m == 0)]
pick = pd.concat([b0[b0.kind == k].sample(min(12, (b0.kind == k).sum()), random_state=SEED) for k in ("flooded_node", "cut_off")])
vm = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "name", "lon", "lat"])
pick = pick.merge(vm[[VID, "name", "lon", "lat"]], on=VID)
pick.to_csv(DATA / "check4_spotcheck_candidates.csv", index=False)
print("\nsnapping distance (m):\n" + snap_sum.round(3).to_string())
print("\nisolation by radius:\n" + isum.to_string(index=False))
print("\ncanals/rivers within 50 m:\n" + cn.round(3).to_string(index=False))
