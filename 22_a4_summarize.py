"""A4 summary: convergence, per-village travel-time distributions, ensemble vs layers A/B, sensitivity.

Inputs: data/a4/<tag>/draws/draw_*.parquet (21_a4_ensemble.py); layer A/B flood times from
data/a2_flood (v1, same configs); no-road flags from data/a2_flood (no_road_r1000, draw-independent).
Convergence (base): per-village mean and 95th percentile of min_any (r = 0; isolated = +inf for the
percentile, excluded from the mean) using the first N = 10..50 draws vs all 50: max and q99 absolute
difference and the share of villages differing by > 0.5 min; Monte Carlo SE of the per-village mean.
Province metrics per draw (RHAI-weighted shares; deduplicated people for counts): weighted median
normal time, coverage within 60 min under flood (1 km rule, road villages), newly isolated people.
Writes data/a4_village_distributions.parquet, results/tables/a4_convergence.csv,
a4_province_by_draw.csv, a4_province_summary.csv.
"""
import numpy as np
import pandas as pd

from _common import DATA, TABLES, VID, log_env, wquantile

log_env(__file__)
TAGS = [t for t in ("base", "q0x0.5", "q0x2") if (DATA / "a4" / t / "draws").exists()
        and any((DATA / "a4" / t / "draws").glob("*.parquet"))]
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "population", "pop_part2km"])
a2 = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))], ignore_index=True)
a2["config"] = a2["event"]
a2 = a2[(a2.event == "normal") | ((a2.D == 3) & (a2["T"] == 0.6))]
noroad = a2[(a2.event == "normal") & (a2.scenario == "B")].set_index(VID)["no_road_r1000"]


def load(tag):
    fs = sorted((DATA / "a4" / tag / "draws").glob("draw_*.parquet"))
    return pd.concat([pd.read_parquet(f).assign(draw=int(f.stem.split("_")[1])) for f in fs], ignore_index=True)


def province(df, keycols):
    """df: rows = village x config (+ keycols), columns min_any, min_any_r1000."""
    out = []
    df = df.merge(pop, on=VID)
    df["no_road"] = df[VID].map(noroad).astype(bool)
    for k, g in df.groupby(keycols):
        nm = g[g.config == "normal"].set_index(VID)
        r = dict(zip(keycols, k if isinstance(k, tuple) else (k,)))
        r["wmedian_normal"] = wquantile(nm["min_any"].fillna(np.inf), nm["population"], 0.5)
        for ev in ("2022", "2025"):
            fl = g[g.config == ev].set_index(VID)
            road = ~fl["no_road"]
            t = fl["min_any_r1000"]
            r[f"cov60_{ev}"] = float(fl.loc[road & (t <= 60), "population"].sum() / fl.loc[road, "population"].sum())
            newly = road & t.isna() & nm.loc[fl.index, "min_any_r1000"].notna()
            r[f"newly_isolated_people_{ev}"] = float(fl.loc[newly, "pop_part2km"].sum())
            r[f"not_cov60_people_{ev}"] = float(fl.loc[road & ~(t <= 60), "pop_part2km"].sum())
        out.append(r)
    return pd.DataFrame(out)


# layers A and B on the same definitions
lay = province(a2.rename(columns={"scenario": "layer"})[[VID, "layer", "config", "min_any", "min_any_r1000"]], ["layer"])
rows = []
for tag in TAGS:
    E = load(tag)
    pr = province(E[[VID, "draw", "config", "min_any", "min_any_r1000"]], ["draw"]).assign(tag=tag)
    rows.append(pr)
    if tag != "base":
        continue
    # ---- convergence ----------------------------------------------------------------------
    conv = []
    for cfg in ("normal", "2022"):
        X = E[E.config == cfg].pivot(index=VID, columns="draw", values="min_any").sort_index(axis=1)
        full_mean = X.mean(axis=1); full_p95 = X.fillna(np.inf).quantile(0.95, axis=1, interpolation="higher")
        se = X.std(axis=1) / np.sqrt(X.notna().sum(axis=1))
        for n in (10, 20, 30, 40, 50):
            m = X.iloc[:, :n].mean(axis=1); p = X.iloc[:, :n].fillna(np.inf).quantile(0.95, axis=1, interpolation="higher")
            dm = (m - full_mean).abs(); dp = (p - full_p95).replace([np.nan], 0).abs()
            dp = dp.where(np.isfinite(dp), np.nan)
            conv.append({"config": cfg, "N": n, "mean_maxabs": dm.max(), "mean_q99abs": dm.quantile(0.99),
                         "mean_share_gt0.5min": (dm > 0.5).mean(), "p95_maxabs_finite": dp.max(),
                         "p95_share_gt0.5min": (dp > 0.5).mean(),
                         "p95_inf_flag_changes": int((np.isinf(p) != np.isinf(full_p95)).sum()),
                         "mc_se_mean_q50": se.median(), "mc_se_mean_q99": se.quantile(0.99)})
    conv = pd.DataFrame(conv); conv.to_csv(TABLES / "a4_convergence.csv", index=False)
    print("CONVERGENCE (base, vs N = 50):\n" + conv.round(4).to_string(index=False))
    # ---- per-village distributions ---------------------------------------------------------
    rw = []
    for cfg, g in E.groupby("config"):
        X = g.pivot(index=VID, columns="draw", values="min_any"); Xr = g.pivot(index=VID, columns="draw", values="min_any_r1000")
        Xi = X.fillna(np.inf)
        rw.append(pd.DataFrame({VID: X.index, "config": cfg, "mean_min": X.mean(axis=1).to_numpy(),
                                "p05_min": Xi.quantile(0.05, axis=1).to_numpy(), "p50_min": Xi.quantile(0.5, axis=1).to_numpy(),
                                "p95_min": Xi.quantile(0.95, axis=1).to_numpy(),
                                "p_unreachable_r0": X.isna().mean(axis=1).to_numpy(),
                                "p_isolated_r1km": (Xr.isna().mean(axis=1) * (~X.index.map(noroad).astype(bool))).to_numpy(),
                                "mean_primary_min": g.pivot(index=VID, columns="draw", values="min_primary").mean(axis=1).to_numpy()}))
    VD = pd.concat(rw, ignore_index=True)
    VD["no_road_r1000"] = VD[VID].map(noroad)
    VD.to_parquet(DATA / "a4_village_distributions.parquet", index=False, compression="zstd")

pr = pd.concat(rows, ignore_index=True)
pr.to_csv(TABLES / "a4_province_by_draw.csv", index=False)
metrics = [c for c in pr.columns if c not in ("draw", "tag")]
summ = pd.concat({stat: pr.groupby("tag")[metrics].agg(fn) for stat, fn in
                  (("mean", "mean"), ("lo95", lambda s: s.quantile(0.025)), ("hi95", lambda s: s.quantile(0.975)))},
                 axis=1).swaplevel(axis=1).sort_index(axis=1)
summ.columns = [f"{m}_{s}" for m, s in summ.columns]
summ.to_csv(TABLES / "a4_province_summary.csv")
lay.to_csv(TABLES / "a4_layers_AB_same_defs.csv", index=False)
pd.set_option("display.width", 250)
print("\nLAYERS A and B (same definitions):\n" + lay.round(3).to_string(index=False))
print("\nENSEMBLE (mean and 95% range over draws):\n" + summ.T.round(3).to_string())
