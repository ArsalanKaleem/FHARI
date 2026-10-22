"""Pre-A3 check 6: does the shared (B-reproducing) graph drop real roads? + the 17 villages.

(a) The 17 villages RHAI reported as slower under B (> 0.01 min): RHAI A, RHAI B, Paper A (same
    graph) A and B, listed individually.
(b) Dadu cluster (villages 76-78, 2294-2304; 20-56 min slower on the shared graph): compare the
    shared graph with an independent OSM snapshot, the Geofabrik Pakistan extract dated 2026-07-12
    clipped to Sindh major classes (flood-recovery-sindh/data/raw/osm/osm_roads.gpkg). Within 25 km
    of the cluster, report Geofabrik road length (by fclass) NOT within 30 m of any shared-graph
    edge, and the same for the two cached Dadu graph versions. Also report the cluster's shortest
    path on the shared graph under A (facility reached, route length by highway class).
    RHAI's own A snapshot is not available (not in the cache), so it cannot be inspected directly.
Writes results/tables/check6_slower_under_B.csv, check6_dadu_cluster_coverage.csv,
check6_dadu_cluster_paths.csv.
"""
import networkx as nx
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

from _common import FLOOD, DATA, TABLES, VID, PAPER, log_env
import _routing as R

log_env(__file__)
CLUSTER = [76, 77, 78] + list(range(2294, 2305))

# (a) the 17 villages ------------------------------------------------------------------
vm = pd.read_parquet(DATA / "village_master.parquet",
                     columns=[VID, "name", "district", "population", "min_any_A", "min_any_B", "slower_under_B"])
nt = pd.read_parquet(DATA / "a2_normal_times.parquet", columns=[VID, "min_any_A", "min_any_B"])
s17 = vm[vm["slower_under_B"]].merge(nt, on=VID, suffixes=("_rhai", "_paperA"))
s17["rhai_B_minus_A"] = s17["min_any_B_rhai"] - s17["min_any_A_rhai"]
s17["paperA_B_minus_A"] = s17["min_any_B_paperA"] - s17["min_any_A_paperA"]
s17.to_csv(TABLES / "check6_slower_under_B.csv", index=False)
print(f"(a) {len(s17)} villages; on shared graph B-A max = {s17['paperA_B_minus_A'].max():.4f} min\n" +
      s17[[VID, "district", "min_any_A_rhai", "min_any_B_rhai", "min_any_A_paperA", "min_any_B_paperA",
           "rhai_B_minus_A", "paperA_B_minus_A"]].round(3).to_string(index=False))

# (b) Dadu cluster ------------------------------------------------------------------------
gv = gpd.read_file(R.RHAI / "data/sindh_villages.gpkg").to_crs(32642)
cl = gv[gv[VID].isin(CLUSTER)]
dadu_poly = R.districts().to_crs(32642).query("district == 'Dadu'").union_all()
area = cl.geometry.union_all().convex_hull.buffer(25000).intersection(dadu_poly)   # graph covers Dadu only
print(f"cluster villages in Dadu polygon: {cl.within(dadu_poly).sum()}/{len(cl)}; "
      f"min distance of cluster to Dadu boundary: {cl.distance(dadu_poly.boundary).min()/1000:.1f} km")
geof = gpd.read_file(FLOOD / "data/raw/osm/osm_roads.gpkg").to_crs(32642)
geof = geof[geof.intersects(area)].copy()
geof["geometry"] = geof.intersection(area)
cov_rows = []
for host in R.available_graphs("Dadu"):
    e = gpd.read_parquet(PAPER / f"cache/graphs/Dadu__{host}__edges.parquet").to_crs(32642)
    e = e[e.intersects(area.buffer(100))]
    cover = shapely.union_all(e.buffer(30).to_numpy())
    missing = geof.geometry.difference(cover)
    for fc, g in geof.assign(miss_km=missing.length / 1000, tot_km=geof.length / 1000).groupby("fclass"):
        cov_rows.append({"graph": host, "fclass": fc, "geofabrik_km": g.tot_km.sum(),
                         "not_in_graph_km": g.miss_km.sum(), "share_missing": g.miss_km.sum() / g.tot_km.sum()})
    print(f"(b) {host}: graph edges in area {len(e):,}, total km {e.length.sum()/2000:.0f} (two-way halved approx)")
cov = pd.DataFrame(cov_rows)
cov.to_csv(TABLES / "check6_dadu_cluster_coverage.csv", index=False)
print(cov.round(3).to_string(index=False))

G = R.load_graph("Dadu", "overpass.kumi.systems")
fac = R.load_facilities("A")
v, f = R.district_inputs("Dadu", fac)
v, f = R.snap(G, v, f)
src = [n for n in pd.unique(f["node"]) if n in G]
dist, paths = nx.multi_source_dijkstra(G, src, weight="travel_time")
prow = []
for _, r in v[v[VID].isin(CLUSTER)].iterrows():
    p = paths.get(r["node"])
    if p is None:
        prow.append({VID: r[VID], "minutes": np.nan}); continue
    hw = {}
    for a, b in zip(p[:-1], p[1:]):
        d = min(G[a][b].values(), key=lambda x: x["travel_time"])
        h = str(d.get("highway")); hw[h] = hw.get(h, 0) + d["length"] / 1000
    fac_name = f.loc[f["node"] == p[0], "name"].astype(str).head(1).tolist()
    prow.append({VID: r[VID], "minutes": dist[r["node"]] / 60, "facility": fac_name[0] if fac_name else None,
                 "route_km": sum(hw.values()), **{f"km_{k}": round(x, 2) for k, x in hw.items()}})
pp = pd.DataFrame(prow).merge(vm[[VID, "min_any_A"]].rename(columns={"min_any_A": "rhai_A"}), on=VID)
pp.to_csv(TABLES / "check6_dadu_cluster_paths.csv", index=False)
print("\nDadu cluster paths on shared graph (A):\n" + pp.round(2).to_string(index=False))
