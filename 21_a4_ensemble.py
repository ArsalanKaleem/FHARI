"""A4: probabilistic facility layers (Monte Carlo ensemble) and per-village travel-time distributions.

Each draw d = layer B (3,308 facilities, RHAI) + a random placement of each of the 741 unlocated PPHI
facilities, drawn from its A3 distribution over candidate places and "no match" (omitted):
  base       A3 calibrated probabilities as estimated
  q0x0.5     no-match odds x 0.5 (more placements)        } P(no match) sensitivity
  q0x2       no-match odds x 2   (fewer placements)       }
  (q0' = k q0 / (k q0 + 1 - q0); candidate probabilities rescaled by (1 - q0') / (1 - q0))
A placed facility within 250 m of an existing layer-B facility is dropped as a duplicate (RHAI rhai_12
DEDUPE_METRES = 250). Tier = PPHI register tier (737 primary, 3 secondary, 1 unclassified).
Placements are drawn once per draw for the whole province (seeded per draw), then routed per district
with the A2 code path on the shared graph: district + 15 km halo, nearest-node snapping, multi-source
Dijkstra from facilities. Configurations per draw: normal roads; 2022 and 2025 base floods (v1 mask,
D = 3, T = 0.6, bridges open). Stored per village: min_any, min_primary (snapped node, r = 0) and
min_any_r1000 (best reachable node within 1 km; decision 6).
Resumable per district: data/a4/<tag>/by_district/<district>.parquet; then assembled into one
zstd Parquet per draw: data/a4/<tag>/draws/draw_<d>.parquet; placements: data/a4/<tag>/placements.parquet.
Usage: python 21_a4_ensemble.py --tag base --draws 50 [--only Dadu]
"""
import argparse
import time

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from _common import DATA, VID, SEED, log_env, set_seeds
import _routing as R

ap = argparse.ArgumentParser()
ap.add_argument("--tag", choices=["base", "q0x0.5", "q0x2"], default="base")
ap.add_argument("--draws", type=int, default=50)
ap.add_argument("--only", nargs="*")
args = ap.parse_args()
set_seeds()
log_env(__file__)
K_ODDS = {"base": 1.0, "q0x0.5": 0.5, "q0x2": 2.0}[args.tag]
CONFIGS = [("normal", None, None), ("2022", 3, 0.6), ("2025", 3, 0.6)]
OUT = DATA / "a4" / args.tag
(OUT / "by_district").mkdir(parents=True, exist_ok=True)
(OUT / "draws").mkdir(parents=True, exist_ok=True)

# ---- placements (province-wide, once per draw) -------------------------------------------
F = pd.read_parquet(DATA / "a3_facilities.parquet")
P = pd.read_parquet(DATA / "a3_placement_probs.parquet")
U = F[F.label_group != "positive"][["fid", "tier"]].copy()
P = P[P.fid.isin(U.fid)][["fid", "entity", "lon", "lat", "q", "q0"]].copy()
if K_ODDS != 1.0:
    q0n = K_ODDS * P.q0 / (K_ODDS * P.q0 + 1 - P.q0)
    P["q"] = P.q * (1 - q0n) / (1 - P.q0)
    P["q0"] = q0n
fB = R.load_facilities("B")
bxy = fB.to_crs(32642); btree = cKDTree(np.c_[bxy.geometry.x, bxy.geometry.y])
cand_pts = gpd.GeoSeries(gpd.points_from_xy(P.lon, P.lat), crs=4326).to_crs(32642)
P["dup250"] = btree.query(np.c_[cand_pts.x, cand_pts.y], k=1)[0] <= 250.0

pl_path = OUT / "placements.parquet"
if pl_path.exists():
    PL = pd.read_parquet(pl_path)
    assert PL["draw"].nunique() == args.draws, "placements exist for a different number of draws"
else:
    rows = []
    ss = np.random.SeedSequence(SEED).spawn(args.draws)
    groups = [(fid, g) for fid, g in P.groupby("fid", sort=True)]
    for d in range(args.draws):
        rng = np.random.default_rng(ss[d])
        for fid, g in groups:
            probs = np.r_[g.q.to_numpy(), g.q0.iloc[0]]
            k = rng.choice(len(probs), p=probs / probs.sum())
            if k == len(g):
                rows.append({"draw": d, "fid": fid, "outcome": "no_match"})
            else:
                c = g.iloc[k]
                rows.append({"draw": d, "fid": fid, "entity": c.entity, "lon": c.lon, "lat": c.lat,
                             "outcome": "duplicate_250m" if c.dup250 else "placed"})
        for fid in sorted(set(U.fid) - set(P.fid)):           # facility without any candidate
            rows.append({"draw": d, "fid": fid, "outcome": "no_candidate"})
    PL = pd.DataFrame(rows).merge(U, on="fid", how="left")
    PL.to_parquet(pl_path, index=False, compression="zstd")
pc = PL.groupby("draw")["outcome"].value_counts().unstack(fill_value=0)
print(f"[{args.tag}] placements per draw: placed mean {pc.get('placed', 0).mean():.1f} "
      f"(min {pc.get('placed', 0).min()}, max {pc.get('placed', 0).max()}); duplicates mean "
      f"{pc.get('duplicate_250m', 0).mean():.1f}; no-match mean {pc.get('no_match', 0).mean():.1f}")

# ---- routing per district -------------------------------------------------------------
normal = pd.read_parquet(DATA / "a2_normal_times.parquet").set_index(VID)
placed = PL[PL.outcome == "placed"].copy()
names = sorted(normal["district"].unique())
if args.only:
    names = [n for n in names if n in args.only]
for dname in names:
    outp = OUT / "by_district" / f"{R.safe_name(dname)}.parquet"
    if outp.exists():
        print(f"skip {dname}"); continue
    t0 = time.time()
    host = normal.loc[normal.district == dname, "graph"].iloc[0]
    G = R.load_graph(dname, host)
    v, f = R.district_inputs(dname, fB)
    v, f = R.snap(G, v, f)
    dpoly = R.districts().query("district == @dname")
    halo = dpoly.to_crs(32642).buffer(R.HALO_M).to_crs(4326).union_all()
    pp = gpd.GeoDataFrame(placed, geometry=gpd.points_from_xy(placed.lon, placed.lat), crs=4326)
    pp = pp[pp.within(halo)].copy()
    if len(pp):
        upts = pp[["entity", "lon", "lat"]].drop_duplicates("entity")
        upts["node"] = R.ox.distance.nearest_nodes(G, upts.lon.to_numpy(), upts.lat.to_numpy())
        pp = pp.merge(upts[["entity", "node"]], on="entity")
    nodes = pd.DataFrame({n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}, index=["x", "y"]).T
    ng = gpd.GeoSeries(gpd.points_from_xy(nodes.x, nodes.y), crs=4326).to_crs(32642)
    nid = nodes.index.to_numpy()
    vp = v.to_crs(32642)
    near = [nid[c] for c in cKDTree(np.c_[ng.x, ng.y]).query_ball_point(np.c_[vp.geometry.x, vp.geometry.y], 1000)]
    weights = {(ev, D, T): R.hiding_weight(frozenset() if ev == "normal" else
                                           R.closed_edges(dname, host, DATA, ev, D, T))
               for ev, D, T in CONFIGS}
    rows = []
    for d in range(args.draws):
        pd_d = pp[pp["draw"] == d] if len(pp) else pp
        src_any = {n for n in f["node"] if n in G}
        src_pri = {n for n in f.loc[f.tier == "primary", "node"] if n in G}
        if len(pd_d):
            src_any |= set(pd_d["node"])
            src_pri |= set(pd_d.loc[pd_d.tier == "primary", "node"])
        for (ev, D, T), w in weights.items():
            ta = nx.multi_source_dijkstra_path_length(G, list(src_any), weight=w)
            tp = nx.multi_source_dijkstra_path_length(G, list(src_pri), weight=w) if src_pri else {}
            rows.append(pd.DataFrame({
                VID: v[VID].to_numpy(), "draw": d, "config": ev,
                "min_any": np.array([ta.get(n, np.nan) for n in v["node"]], np.float32) / 60,
                "min_primary": np.array([tp.get(n, np.nan) for n in v["node"]], np.float32) / 60,
                "min_any_r1000": np.array([min((ta[n] for n in c if n in ta), default=np.nan) for c in near], np.float32) / 60,
                "n_placed_in_halo": len(pd_d)}))
    out = pd.concat(rows, ignore_index=True)
    out["district"] = dname
    # sanity: a draw's normal times can never exceed layer B's (superset of facilities, same graph)
    nb = normal.loc[v[VID], "min_any_B"].to_numpy()
    for d in range(args.draws):
        x = out[(out.draw == d) & (out.config == "normal")]["min_any"].to_numpy()
        bad = (x > nb + 1e-4) & ~np.isnan(nb)
        assert not bad.any(), f"{dname} draw {d}: {bad.sum()} villages slower than layer B"
    out.to_parquet(outp, index=False, compression="zstd")
    print(f"{dname:16s} villages={len(v)} placed-in-halo mean={out.groupby('draw').n_placed_in_halo.first().mean():.1f} "
          f"({time.time()-t0:.0f}s)", flush=True)
    del G

# ---- assemble one file per draw ---------------------------------------------------------
parts = sorted((OUT / "by_district").glob("*.parquet"))
if len(parts) == len(sorted(normal["district"].unique())) and not args.only:
    allv = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    assert allv.groupby(["draw", "config"])[VID].nunique().eq(5159).all()
    for d, g in allv.groupby("draw"):
        g.drop(columns=["draw"]).to_parquet(OUT / "draws" / f"draw_{d:03d}.parquet", index=False, compression="zstd")
    print(f"assembled {allv['draw'].nunique()} draw files in {OUT / 'draws'}")
