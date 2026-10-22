"""A2: flood-conditioned routing — 2x2 (normal vs flood roads) x (Scenario A vs B), by threshold.

Exposure-based closure scenarios (NOT observed closures). An edge is closed when
    frac_fd_ge{D} >= T     (share of its unmasked sampled length with >= D flood-days)
for T in {0.3, 0.6, 0.9} and D in {1, 3, 5}; base scenario T = 0.6, D = 3 (T = 0.6 matches
Khan et al. 2026). Events: 2022, 2025. Edges tagged as bridges in OSM are never closed in the
base run (water under a bridge is expected).
Options:
  --mask v1|v2|v2s25   flood-mask version (segment_exposure[_v2|_v2s25]); v1 = A1 as built
  --close-bridges      sensitivity: bridges closable
  --embankment         pre-registered sensitivity: trunk and primary roads never closed
Both scenarios use the same graph per district as the normal baseline (07). Closures are applied
through a Dijkstra weight function that hides closed edges (no graph copy).

Per village and configuration:
  min_<tier>        time at the village's snapped node (RHAI rule; NaN = unreachable)  [r = 0]
  min_any_r500 / r1000 / r2000   best time over facility-reachable nodes within 0.5 / 1 / 2 km of the
                    village point (decision 6: flood isolation = NaN at r = 1 km; off-road leg untimed)
  no_road_r<r>      no road node at all within r ("no mapped road access" at that radius; separate
                    category: isolated at radius r = min_any_r<r> is NaN AND not no_road_r<r>)
Resumable per district: data/a2_flood[_<mask>][_bridges][_emb]/<district>.parquet. The "normal"
pass is checked against data/a2_normal_times.parquet.
"""
import argparse
import time

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from _common import DATA, VID, log_env, set_seeds
import _routing as R

ap = argparse.ArgumentParser()
ap.add_argument("--mask", choices=["v1", "v2", "v2s25"], default="v1")
ap.add_argument("--close-bridges", action="store_true")
ap.add_argument("--embankment", action="store_true")
ap.add_argument("--only", nargs="*", help="district names")
args = ap.parse_args()
set_seeds()
log_env(__file__)

T_LIST, D_LIST, EVENTS = (0.3, 0.6, 0.9), (1, 3, 5), ("2022", "2025")
RADII = (500, 1000, 2000)
TIERS = ("any",) + R.TIERS
EMB_CLASSES = ("trunk", "primary")
suffix = ("" if args.mask == "v1" else f"_{args.mask}") + ("_bridges" if args.close_bridges else "") + \
         ("_emb" if args.embankment else "")
OUT = DATA / f"a2_flood{suffix}"
EXPO = DATA / ("segment_exposure" if args.mask == "v1" else f"segment_exposure_{args.mask}")
OUT.mkdir(parents=True, exist_ok=True)
normal = pd.read_parquet(DATA / "a2_normal_times.parquet").set_index(VID)
fac = {s: R.load_facilities(s) for s in ("A", "B")}


def make_weight(closed):
    if not closed:
        return "travel_time"

    def w(u, v, d):
        best = None
        for k, a in d.items():
            if (u, v, k) in closed:
                continue
            t = a["travel_time"]
            if best is None or t < best:
                best = t
        return best                     # None hides the edge from Dijkstra
    return w


def route_closed(G, v, f, weight, near):
    out = {}
    for tier in TIERS:
        sub = f if tier == "any" else f[f["tier"] == tier]
        if not len(sub):
            continue
        src = [n for n in pd.unique(sub["node"]) if n in G]
        tt = nx.multi_source_dijkstra_path_length(G, src, weight=weight) if src else {}
        out[f"min_{tier}"] = np.array([tt.get(n, np.nan) / 60.0 for n in v["node"]])
        if tier == "any":
            for r, nb in near.items():
                out[f"min_any_r{r}"] = np.array([min((tt[n] for n in c if n in tt), default=np.nan) / 60.0
                                                 for c in nb])
    return out


names = sorted(normal["district"].unique())
if args.only:
    names = [d for d in names if d in args.only]
for dname in names:
    out_path = OUT / f"{R.safe_name(dname)}.parquet"
    if out_path.exists():
        print(f"skip {dname}"); continue
    t0 = time.time()
    host = normal.loc[normal["district"] == dname, "graph"].iloc[0]
    expo = pd.read_parquet(EXPO / f"{R.safe_name(dname)}__{host}.parquet")
    edges = pd.read_parquet(DATA.parent / f"cache/graphs/{R.safe_name(dname)}__{host}__edges.parquet")
    if "bridge" not in edges.columns:          # no OSM bridge tags in this district's graph
        edges["bridge"] = None
    edges = edges[["u", "v", "key", "bridge"]]
    expo = expo.merge(edges, on=["u", "v", "key"], how="left", validate="one_to_one")
    is_bridge = expo["bridge"].fillna("nan").astype(str).str.lower().isin(["yes", "true", "viaduct"]) | \
        expo["bridge"].astype(str).str.contains("yes", case=False, na=False)
    # OSM highway may be a list-string, e.g. "['primary', 'secondary']": any trunk/primary(_link) counts
    is_emb = expo["highway"].astype(str).str.contains(r"\b(?:trunk|primary)(?:_link)?\b", regex=True)
    G = R.load_graph(dname, host)
    nodes = pd.DataFrame({n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}, index=["x", "y"]).T
    ng = gpd.GeoSeries(gpd.points_from_xy(nodes.x, nodes.y), crs=4326).to_crs(32642)
    tree = cKDTree(np.c_[ng.x, ng.y]); nid = nodes.index.to_numpy()
    snapped, near, noroad = {}, {}, {}
    for s in ("A", "B"):
        v, f = R.district_inputs(dname, fac[s])
        snapped[s] = R.snap(G, v, f)
        vp = v.to_crs(32642); vxy = np.c_[vp.geometry.x, vp.geometry.y]
        near[s] = {r: [nid[c] for c in tree.query_ball_point(vxy, r)] for r in RADII}
        noroad[s] = {r: np.array([len(c) == 0 for c in near[s][r]]) for r in RADII}
    rows, n_closed, cache = [], {}, {}
    configs = [("normal", None, None)] + [(e, d, t) for e in EVENTS for d in D_LIST for t in T_LIST]
    for ev, D, T in configs:
        if ev == "normal":
            mask = np.zeros(len(expo), bool)
        else:
            frac = expo[f"y{ev}_frac_fd_ge{D}"].to_numpy()
            mask = np.nan_to_num(frac, nan=0.0) >= T
            if not args.close_bridges:
                mask &= ~is_bridge.to_numpy()
            if args.embankment:
                mask &= ~is_emb.to_numpy()
        closed = frozenset(map(tuple, expo.loc[mask, ["u", "v", "key"]].itertuples(index=False, name=None)))
        n_closed[(ev, D, T)] = len(closed)
        for s in ("A", "B"):
            v, f = snapped[s]
            key = (closed, s)
            if key not in cache:                 # identical closure sets are routed once
                cache[key] = route_closed(G, v, f, make_weight(closed), near[s])
            df = pd.DataFrame({VID: v[VID].to_numpy(), **cache[key]})
            for r in RADII:
                df[f"no_road_r{r}"] = noroad[s][r]
            df["scenario"], df["event"], df["D"], df["T"] = s, ev, D, T
            df["n_closed_edges"], df["n_edges"] = len(closed), len(expo)
            rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out["district"], out["mask"] = dname, args.mask
    nm = out[out["event"] == "normal"]
    for s in ("A", "B"):
        a = nm[nm["scenario"] == s].set_index(VID)["min_any"]
        b = normal.loc[a.index, f"min_any_{s}"]
        bad = ~((a - b).abs().le(1e-6) | (a.isna() & b.isna()))
        assert not bad.any(), f"{dname} {s}: normal pass differs from 07 baseline in {bad.sum()} villages"
    out.to_parquet(out_path, index=False)
    print(f"{dname:16s} edges={len(expo):,} closed(2022,D3,T0.6)={n_closed[('2022', 3, 0.6)]:,} "
          f"unique closure sets={len(cache)//2}  ({time.time()-t0:.0f}s)", flush=True)
    del G, cache
