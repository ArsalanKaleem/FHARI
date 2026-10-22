"""A7 main run (docs/prereg_A7.md, frozen 2026-10-20): single-link gains, candidate set, greedy allocations
for layer A, layer B, the ensemble (expected value over draws) and each draw (x*_d), and exact evaluation
of every allocation on every draw.

Config (CLI): --event 2022|2025 --D 3 --T 0.6 [--embankment] [--close-bridges] --N 200 --Kmax 50
Mask: v1 (pre-registered verdict 2026-10-21). States: A, B, draws 0..49 of data/a4/base (B + placements).
Objectives (gains, positive = better), all from the same village-time changes:
  cov60  (PRIMARY) RHAI-weighted population newly within 60 min; cov30, cov120 sensitivity
  iso    RHAI-weighted population newly reachable (isolation reduction)
  ph     reduction in added person-hours (dedup pop) among villages reachable normally and under flood
  eq1, eq2  cov60 with priority weights pop * (t_normal / t_med)^eps, eps = 1, 2
Candidate set: union of top N links under A, B and the ensemble mean, ranked by single-link cov60 gain
(ties by link id), shared by all objectives (prereg §4).
Greedy: per objective and state, add the candidate with the largest marginal gain (exact, incremental),
ties by link id, up to Kmax; the ensemble allocation maximises the mean gain over draws.
Evaluation: each allocation prefix (K = 5, 10, 20, 50 [, 100]) is applied exactly to every draw and to A
and B; all objectives recorded (RHAI-weighted and dedup).
Outputs data/a7/<cfg>/: links.parquet, single_gains.parquet, candidates.parquet, allocations.parquet,
values.parquet. Resumable at the stage level.
"""
import argparse
import time

import geopandas as gpd
import numpy as np
import pandas as pd

from _common import DATA, VID, log_env, set_seeds, wquantile
import _routing as R
import _a7 as E

ap = argparse.ArgumentParser()
ap.add_argument("--event", default="2022"); ap.add_argument("--D", type=int, default=3)
ap.add_argument("--T", type=float, default=0.6)
ap.add_argument("--embankment", action="store_true"); ap.add_argument("--close-bridges", action="store_true")
ap.add_argument("--N", type=int, default=200); ap.add_argument("--Kmax", type=int, default=50)
ap.add_argument("--draws", type=int, default=50)
ap.add_argument("--length-km", type=float, default=None,
                help="length-weighted budget (prereg sensitivity): greedy by gain per km until sum km <= L")
args = ap.parse_args()
set_seeds(); log_env(__file__)
CFG = f"{args.event}_D{args.D}_T{args.T}" + ("_emb" if args.embankment else "") + \
      ("_bridges" if args.close_bridges else "") + f"_N{args.N}_K{args.Kmax}" + \
      (f"_L{args.length_km:g}" if args.length_km else "")
OUT = DATA / "a7" / CFG
OUT.mkdir(parents=True, exist_ok=True)
OBJ = ["cov60", "cov30", "cov120", "iso", "ph", "eq1", "eq2"]
KS = [k for k in (5, 10, 20, 50, 100) if k <= args.Kmax]
STATES = ["A", "B"] + [f"d{i:02d}" for i in range(args.draws)]
DRAWS = [s for s in STATES if s.startswith("d")]

nt = pd.read_parquet(DATA / "a2_normal_times.parquet").set_index(VID)
popdf = pd.read_parquet(DATA / "village_population_alt.parquet").set_index(VID)
PL = pd.read_parquet(DATA / "a4/base/placements.parquet")
PL = PL[(PL.outcome == "placed") & (PL["draw"] < args.draws)]
facB = R.load_facilities("B"); facA = R.load_facilities("A")

# province-wide normal r0 times per state, for equity weights (t_med = pop-weighted median)
a4n = {d: pd.read_parquet(DATA / f"a4/base/draws/draw_{d:03d}.parquet").query("config == 'normal'").set_index(VID)["min_any"]
       for d in range(args.draws)}
tnorm_r0 = {"A": nt["min_any_A"], "B": nt["min_any_B"], **{f"d{d:02d}": a4n[d] for d in range(args.draws)}}
tmed = {s: wquantile(tnorm_r0[s].fillna(np.inf), popdf.loc[tnorm_r0[s].index, "population"], 0.5) for s in STATES}


def eq_weight(s, vids, eps):
    t = tnorm_r0[s].loc[vids].to_numpy(float)
    finite = np.isfinite(t)
    w = np.where(finite, (np.maximum(t, 1e-6) / tmed[s]) ** eps, np.nan)
    w = np.where(finite, w, np.nanmax(w))        # isolated even normally: max finite weight
    return popdf.loc[vids, "population"].to_numpy() * w


def sources(D, s, fac_nodes_cache):
    if s in fac_nodes_cache:
        return fac_nodes_cache[s]
    if s in ("A", "B"):
        _, f = R.district_inputs(D.name, facA if s == "A" else facB)
        nodes = R.ox.distance.nearest_nodes(D._G, f.geometry.x.to_numpy(), f.geometry.y.to_numpy())
        src = np.array([D.idx[n] for n in nodes])
    else:
        src = fac_nodes_cache["B"]
        pp = D.placed[D.placed["draw"] == int(s[1:])]
        if len(pp):
            src = np.r_[src, pp["nidx"].to_numpy()]
    fac_nodes_cache[s] = src
    return src


t_start = time.time()
names = sorted(nt["district"].unique())
dist_data = {}
link_rows, gain_rows, base_rows = [], [], []
for dname in names:
    t0 = time.time()
    host = nt.loc[nt.district == dname, "graph"].iloc[0]
    D = E.load_district(dname, host)
    D.idx = {n: i for i, n in enumerate(D.nodes)}
    halo = R.districts().query("district == @dname").to_crs(32642).buffer(R.HALO_M).to_crs(4326).union_all()
    pp = gpd.GeoDataFrame(PL, geometry=gpd.points_from_xy(PL.lon, PL.lat), crs=4326)
    pp = pp[pp.within(halo)].copy()
    if len(pp):
        u = pp.drop_duplicates("entity")
        u = u.assign(nidx=[D.idx[n] for n in R.ox.distance.nearest_nodes(D._G, u.lon.to_numpy(), u.lat.to_numpy())])
        pp = pp.merge(u[["entity", "nidx"]], on="entity")
    D.placed = pp
    closed = E.closed_mask(D, R.closed_edges(dname, host, DATA, args.event, args.D, args.T,
                                             embankment=args.embankment, close_bridges=args.close_bridges))
    links = E.build_links(D, closed)
    M_open, M_all = E.csr(D, ~closed), E.csr(D, np.ones(len(D.eu), bool))
    vids = D.vid
    w = {"rhai": popdf.loc[vids, "population"].to_numpy(), "dedup": popdf.loc[vids, "pop_part2km"].to_numpy()}
    cache, states = {}, {}
    for s in STATES:
        src = sources(D, s, cache)
        tn = E.village_times(D, E.node_dist(M_all, src))
        st = E.State(D, M_open, src, tn)
        st.w_eq = {1: eq_weight(s, vids, 1), 2: eq_weight(s, vids, 2)}
        states[s] = st
        base_rows.append({"district": dname, "state": s, "vids": vids, "t_flood": st.t.copy(), "t_normal": tn})
    dist_data[dname] = (D, links, states, w)
    for li, lk in enumerate(links):
        lid = f"{dname}|{li}"
        link_rows.append({"link": lid, "district": dname, "n_edges": len(lk["edges"]), "length_km": lk["length_km"],
                          "ends": lk["ends"]})
        for s in STATES:
            st = states[s]
            vd = st.village_delta(st.improve(lk))
            gains = {}
            for T in (60, 30, 120):
                gc, gi, gp = E.objective_gain(st, vd, w["rhai"], w["rhai"], w["dedup"], T)
                gains[f"cov{T}"] = gc
                if T == 60:
                    gains["iso"], gains["ph"] = gi, gp
                    gains["cov60_dedup"] = E.objective_gain(st, vd, w["dedup"], w["dedup"], w["dedup"], 60)[0]
                    gains["eq1"] = E.objective_gain(st, vd, st.w_eq[1], w["rhai"], w["dedup"], 60)[0]
                    gains["eq2"] = E.objective_gain(st, vd, st.w_eq[2], w["rhai"], w["dedup"], 60)[0]
            gain_rows.append({"link": lid, "state": s, **gains})
    print(f"{dname:16s} closed {closed.sum():,} links {len(links):,}  ({time.time()-t0:.0f}s, total {time.time()-t_start:.0f}s)", flush=True)

links_df = pd.DataFrame(link_rows); G1 = pd.DataFrame(gain_rows)
links_df.drop(columns="ends").to_parquet(OUT / "links.parquet", index=False)
LEN = links_df.set_index("link")["length_km"].to_dict()
G1.to_parquet(OUT / "single_gains.parquet", index=False, compression="zstd")

# ---- candidate set (prereg §4) ----------------------------------------------------------------
def top(series, n):
    s = series.reset_index(); s.columns = ["link", "g"]
    return set(s.sort_values(["g", "link"], ascending=[False, True]).head(n)["link"])


gA = G1[G1.state == "A"].set_index("link")["cov60"]; gB = G1[G1.state == "B"].set_index("link")["cov60"]
gE = G1[G1.state.isin(DRAWS)].groupby("link")["cov60"].mean()
CAND = sorted(top(gA, args.N) | top(gB, args.N) | top(gE, args.N))
pd.DataFrame({"link": CAND}).to_parquet(OUT / "candidates.parquet", index=False)
print(f"candidates: {len(CAND)} (positive single gain under any state: "
      f"{int((G1[G1.link.isin(CAND)].groupby('link').cov60.max() > 0).sum())})", flush=True)
cand_by_d = {}
for lid in CAND:
    d, i = lid.split("|"); cand_by_d.setdefault(d, []).append((lid, int(i)))


def gain_of(st, lk, w, obj):
    vd = st.village_delta(st.improve(lk))
    if obj.startswith("cov"):
        return E.objective_gain(st, vd, w["rhai"], w["rhai"], w["dedup"], int(obj[3:]))[0], vd
    if obj == "iso":
        return E.objective_gain(st, vd, w["rhai"], w["rhai"], w["dedup"], 60)[1], vd
    if obj == "ph":
        return E.objective_gain(st, vd, w["rhai"], w["rhai"], w["dedup"], 60)[2], vd
    return E.objective_gain(st, vd, st.w_eq[int(obj[2:])], w["rhai"], w["dedup"], 60)[0], vd


def fresh(s):
    """Fresh copy of each district's state s (independent distance arrays)."""
    out = {}
    for d, (D, links, states, w) in dist_data.items():
        st0 = states[s]
        st = E.State.__new__(E.State)
        st.__dict__.update(st0.__dict__); st.d = st0.d.copy(); st.t = st0.t.copy(); st.extra = {}
        out[d] = st
    return out


def greedy(state_keys, obj):
    """Greedy over candidates maximising the MEAN gain across the given states (1 state = plain greedy)."""
    S = {s: fresh(s) for s in state_keys}
    cur = {}
    for d, lst in cand_by_d.items():
        D, links, _, w = dist_data[d]
        for lid, i in lst:
            cur[lid] = np.mean([gain_of(S[s][d], links[i], w, obj)[0] for s in state_keys])
    chosen, rem = [], args.length_km
    for _ in range(min(args.Kmax, len(cur))):
        if rem is None:
            best = sorted(((g, lid) for lid, g in cur.items()), key=lambda x: (-x[0], x[1]))[0][1]
        else:                                   # length budget: best gain per km among links that still fit
            fit = [(g / max(LEN[lid], 1e-3), lid) for lid, g in cur.items() if LEN[lid] <= rem and g > 0]
            if not fit:
                break
            best = sorted(fit, key=lambda x: (-x[0], x[1]))[0][1]
            rem -= LEN[best]
        d, i = best.split("|"); D, links, _, w = dist_data[d]
        for s in state_keys:
            st = S[s][d]; st.commit(links[int(i)], st.improve(links[int(i)]))
        chosen.append(best); del cur[best]
        for lid, j in cand_by_d[d]:
            if lid in cur:
                cur[lid] = np.mean([gain_of(S[s][d], links[j], w, obj)[0] for s in state_keys])
    return chosen


def evaluate(alloc, s):
    """Exact objective values of allocation prefixes on state s (province totals)."""
    S = fresh(s)
    rows = []

    def snapshot(k):
        r = {"K": k}
        tf, tn, wr, wd, e1, e2, nr = [], [], [], [], [], [], []
        for d, (D, links, states, w) in dist_data.items():
            st = S[d]; tf.append(st.t); tn.append(st.t_normal); wr.append(w["rhai"]); wd.append(w["dedup"])
            e1.append(st.w_eq[1]); e2.append(st.w_eq[2]); nr.append(D.no_road)
        tf, tn, wr, wd, e1, e2, nr = map(np.concatenate, (tf, tn, wr, wd, e1, e2, nr))
        road = ~nr
        for T in (30, 60, 120):
            r[f"cov{T}"] = float(wr[road & (tf <= T)].sum() / wr[road].sum())
            r[f"cov{T}_dedup"] = float(wd[road & (tf <= T)].sum())
        r["iso_rhai"] = float(wr[road & ~np.isfinite(tf)].sum()); r["iso_dedup"] = float(wd[road & ~np.isfinite(tf)].sum())
        both = road & np.isfinite(tf) & np.isfinite(tn)
        r["ph_dedup"] = float(((tf[both] - tn[both]) * wd[both] / 60).sum())
        r["eq1"] = float(e1[road & (tf <= 60)].sum() / e1[road].sum()); r["eq2"] = float(e2[road & (tf <= 60)].sum() / e2[road].sum())
        tc = np.where(np.isfinite(tf[road]), np.minimum(tf[road], 120), 120) + 1.0   # +1 min offset (zeros)
        r["atkinson1_time"] = float(1 - np.exp(np.average(np.log(tc), weights=wr[road])) / np.average(tc, weights=wr[road]))
        rows.append(r)

    snapshot(0)
    for k, lid in enumerate(alloc, start=1):
        d, i = lid.split("|"); D, links, _, w = dist_data[d]
        st = S[d]; st.commit(links[int(i)], st.improve(links[int(i)]))
        if args.length_km is None and k in KS:
            snapshot(k)
    if args.length_km is not None:              # length budget: one evaluation of the whole allocation
        snapshot(len(alloc)); rows[-1]["length_km"] = float(sum(LEN[l] for l in alloc))
    return rows


alloc_path = OUT / "allocations.parquet"
if alloc_path.exists():
    AL = pd.read_parquet(alloc_path)
else:
    al = []
    for obj in OBJ:
        t0 = time.time()
        for who, keys in [("A", ["A"]), ("B", ["B"]), ("ens", DRAWS)] + [(f"opt_{s}", [s]) for s in DRAWS]:
            for rank, lid in enumerate(greedy(keys, obj), start=1):
                al.append({"objective": obj, "alloc": who, "rank": rank, "link": lid})
        print(f"greedy {obj}: {time.time()-t0:.0f}s", flush=True)
    AL = pd.DataFrame(al); AL.to_parquet(alloc_path, index=False)

vals = []
t0 = time.time()
for obj in OBJ:
    A_ = AL[AL.objective == obj]
    for who in ["A", "B", "ens"]:
        alloc = A_[A_.alloc == who].sort_values("rank")["link"].tolist()
        for s in STATES:
            vals += [{"objective": obj, "alloc": who, "state": s, **r} for r in evaluate(alloc, s)]
    for s in DRAWS:
        alloc = A_[A_.alloc == f"opt_{s}"].sort_values("rank")["link"].tolist()
        vals += [{"objective": obj, "alloc": "opt", "state": s, **r} for r in evaluate(alloc, s)]
    print(f"evaluated {obj}: {time.time()-t0:.0f}s", flush=True)
pd.DataFrame(vals).to_parquet(OUT / "values.parquet", index=False)
print(f"DONE {CFG} in {time.time()-t_start:.0f}s")
