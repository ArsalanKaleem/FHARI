"""A7 analysis (prereg_A7 §§6-9): regret, EVPI, overlap, ILP-approx check, EVPPI, equity frontier.

Input: data/a7/<cfg>/ from 25_a7_run.py. Value V per objective (higher = better):
  cov30/60/120: RHAI-weighted coverage share (absolute: cov*_dedup people)
  iso: -isolated RHAI population (absolute: iso_dedup)     ph: -added person-hours (dedup)
  eq1/eq2: priority-weighted coverage share
Headline Regret(x) = E_d[V_d(x*_d) - V_d(x)] / E_d[V_d(x*_d) - V_d(empty)]; absolute regret in dedup
people / person-hours; coverage-normalised RegretC = E_d[V(x*) - V(x)] / E_d[V(x*)] (coverage objectives).
x*_d is the GREEDY optimum for draw d (an approximation); draws where x beats x*_d are counted.
Tiny-gain rule: achievable gain < 1,000 dedup people (or person-hours for ph) or its 95 % interval
includes 0 -> ratio not headline (flag `ratio_headline` False).
EVPI = E_d[V(x*_d)] - E_d[V(x_ens)]. Intervals: percentile bootstrap over draws (2,000, seed 20221001).
ILP check: top-K by single-link gain (unit-cost knapsack, solved exactly by sorting) vs greedy, Jaccard at
K = 20. EVPPI_k (additive approximation): per-draw single-link gains, district k resolved, others at the
ensemble mean; validated against the exact province EVPI (deviation from prereg: exact per-district
validation exceeds the compute budget; logged).
Writes results/tables/a7_<cfg>_*.csv
"""
import sys

import numpy as np
import pandas as pd

from _common import DATA, TABLES, SEED, log_env

log_env(__file__)
CFG = sys.argv[1] if len(sys.argv) > 1 else "2022_D3_T0.6_N200_K50"
IN = DATA / "a7" / CFG
V = pd.read_parquet(IN / "values.parquet")
AL = pd.read_parquet(IN / "allocations.parquet")
G1 = pd.read_parquet(IN / "single_gains.parquet")
CAND = set(pd.read_parquet(IN / "candidates.parquet")["link"])
rng = np.random.default_rng(SEED)
DR = sorted(s for s in V.state.unique() if s.startswith("d"))
KS = sorted(k for k in V.K.unique() if k > 0)
K0 = 20 if 20 in KS else max(KS)          # reference budget for ILP check / EVPPI
VAL = {"cov60": ("cov60", "cov60_dedup", 1), "cov30": ("cov30", "cov30_dedup", 1), "cov120": ("cov120", "cov120_dedup", 1),
       "iso": ("iso_rhai", "iso_dedup", -1), "ph": ("ph_dedup", "ph_dedup", -1), "eq1": ("eq1", None, 1), "eq2": ("eq2", None, 1)}


def ci(x, stat):
    b = [stat(x[rng.integers(0, len(x), len(x))]) for _ in range(2000)]
    return np.nanpercentile(b, [2.5, 97.5])


rows, jac = [], []
for obj, (col, abscol, sign) in VAL.items():
    v = V[V.objective == obj]
    for K in KS:
        def get(alloc, c, k=K):
            x = v[(v.alloc == alloc) & (v.K == k) & v.state.isin(DR)].set_index("state")[c]
            return sign * x.loc[DR].to_numpy(float)
        opt, empty = get("opt", col), get("opt", col, 0)
        ach = opt - empty
        absc = abscol or col
        opt_a, empty_a = get("opt", absc), get("opt", absc, 0)
        ach_abs = opt_a - empty_a
        ach_ci = ci(ach_abs, np.mean)
        # tiny-gain rule (prereg §8) is defined in people / person-hours; eq1/eq2 values are weighted shares,
        # so the rule is not applicable there (flag None)
        tiny = None if abscol is None else ((ach_abs.mean() < 1000) or (ach_ci[0] <= 0 <= ach_ci[1]))
        for alloc in ("A", "B", "ens"):
            x, xa = get(alloc, col), get(alloc, absc)
            sh = opt - x
            reg = sh.mean() / ach.mean() if ach.mean() != 0 else np.nan
            idx = np.arange(len(DR))
            boot = []
            for _ in range(2000):
                s = rng.integers(0, len(DR), len(DR))
                boot.append((sh[s].mean() / ach[s].mean()) if ach[s].mean() != 0 else np.nan)
            lo, hi = np.nanpercentile(boot, [2.5, 97.5])
            ra = (opt_a - xa)
            rows.append({"objective": obj, "K": K, "alloc": alloc,
                         "regret_share": reg, "regret_lo95": lo, "regret_hi95": hi,
                         "abs_regret_mean": ra.mean(), "abs_regret_lo95": ci(ra, np.mean)[0], "abs_regret_hi95": ci(ra, np.mean)[1],
                         "regretC_cov_norm": (sh.mean() / opt.mean()) if obj.startswith("cov") else np.nan,
                         "achievable_abs_mean": ach_abs.mean(), "achievable_abs_lo95": ach_ci[0], "achievable_abs_hi95": ach_ci[1],
                         "ratio_headline": None if tiny is None else (not tiny), "share_draws_x_beats_greedy_opt": float((sh < -1e-12).mean())})
        evpi = (opt - get("ens", col)); evpi_a = (opt_a - get("ens", absc))
        rows.append({"objective": obj, "K": K, "alloc": "EVPI", "abs_regret_mean": evpi_a.mean(),
                     "abs_regret_lo95": ci(evpi_a, np.mean)[0], "abs_regret_hi95": ci(evpi_a, np.mean)[1],
                     "regret_share": evpi.mean() / ach.mean() if ach.mean() else np.nan})
        a = AL[AL.objective == obj]
        sets = {w: set(a[(a.alloc == w) & (a["rank"] <= K)]["link"]) for w in a.alloc.unique()}
        J = lambda p, q: len(p & q) / len(p | q) if (p | q) else np.nan
        jac.append({"objective": obj, "K": K, "J_A_B": J(sets["A"], sets["B"]), "J_A_ens": J(sets["A"], sets["ens"]),
                    "J_B_ens": J(sets["B"], sets["ens"]),
                    "meanJ_A_opt": np.mean([J(sets["A"], sets[f"opt_{s}"]) for s in DR]),
                    "meanJ_B_opt": np.mean([J(sets["B"], sets[f"opt_{s}"]) for s in DR]),
                    "meanJ_ens_opt": np.mean([J(sets["ens"], sets[f"opt_{s}"]) for s in DR])})
R_ = pd.DataFrame(rows); J_ = pd.DataFrame(jac)
R_.to_csv(TABLES / f"a7_{CFG}_regret.csv", index=False); J_.to_csv(TABLES / f"a7_{CFG}_jaccard.csv", index=False)

# ---- ILP (additive) check at K = 20, primary objective ------------------------------------------
gc = G1[G1.link.isin(CAND)]
ilp = []
for who, st in (("A", ["A"]), ("B", ["B"]), ("ens", DR)):
    g = gc[gc.state.isin(st)].groupby("link")["cov60"].mean().reset_index()
    top = set(g.sort_values(["cov60", "link"], ascending=[False, True]).head(K0)["link"])
    gr = set(AL[(AL.objective == "cov60") & (AL.alloc == who) & (AL["rank"] <= K0)]["link"])
    j = len(top & gr) / len(top | gr)
    ilp.append({"alloc": who, "K": K0, "jaccard_greedy_vs_additive": j, "flag_lt_0.8": j < 0.8})
pd.DataFrame(ilp).to_csv(TABLES / f"a7_{CFG}_ilp_check.csv", index=False)

# ---- EVPPI per district (additive approximation), K = 20, cov60 dedup ---------------------------
g = gc[gc.state.isin(DR)].pivot(index="link", columns="state", values="cov60_dedup")[DR]
gmean = g.mean(axis=1)
base_val = np.sort(gmean.to_numpy())[::-1][:K0].sum()
evpi_add = np.mean([np.sort(g[s].to_numpy())[::-1][:K0].sum() for s in DR]) - base_val
dist = g.index.str.split("|").str[0]
ev = []
for k in sorted(set(dist)):
    m = (dist == k)
    vals = []
    for s in DR:
        cond = np.where(m, g[s].to_numpy(), gmean.to_numpy())
        vals.append(np.sort(cond)[::-1][:K0].sum())
    ev.append({"district": k, "K": K0, "EVPPI_dedup_people": np.mean(vals) - base_val, "n_candidate_links": int(m.sum())})
EV = pd.DataFrame(ev).sort_values("EVPPI_dedup_people", ascending=False)
exact = R_[(R_.objective == "cov60") & (R_.K == K0) & (R_.alloc == "EVPI")]["abs_regret_mean"].iloc[0]
EV.to_csv(TABLES / f"a7_{CFG}_evppi.csv", index=False)
pd.DataFrame([{"K": K0, "evpi_additive_dedup": evpi_add, "evpi_exact_dedup": exact}]).to_csv(
    TABLES / f"a7_{CFG}_evppi_validation.csv", index=False)

# ---- equity frontier ---------------------------------------------------------------------
fr = V[V.objective.isin(["cov60", "eq1", "eq2"])].copy()
fr["eps"] = fr.objective.map({"cov60": 0, "eq1": 1, "eq2": 2})
FRm = fr.assign(sgrp=np.where(fr.state.str.startswith("d"), "draws_mean", fr.state)).groupby(["eps", "alloc", "K", "sgrp"])[["cov60", "atkinson1_time"]].mean().reset_index()
FRm.to_csv(TABLES / f"a7_{CFG}_equity_frontier.csv", index=False)

pd.set_option("display.width", 250)
print(f"== {CFG}\nREGRET (headline = share of achievable benefit; abs in dedup people / person-hours):")
print(R_.round(4).to_string(index=False))
print("\nJACCARD:\n" + J_.round(3).to_string(index=False))
print("\nILP additive check (K=20, cov60):\n" + pd.DataFrame(ilp).round(3).to_string(index=False))
print(f"\nEVPPI (additive, K={K0}, dedup people): province additive EVPI {evpi_add:.1f} vs exact EVPI {exact:.1f}")
print(EV.head(10).round(1).to_string(index=False))
print(f"\nEQUITY FRONTIER (K={K0}):\n" + FRm[FRm.K == K0].round(4).to_string(index=False))
