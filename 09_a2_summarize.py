"""A2 results: 2x2 (normal vs flood roads) x (A vs B) by event and closure threshold; H1, H2.

All headline figures population-weighted (village `population` = WorldPop within 2 km; buffers of
nearby villages overlap, so totals double-count — see Limitations), with unweighted alongside.
Isolated villages (no path to any facility) are a separate category: they enter medians/p90 as +inf
and are excluded from added-time sums, which cover villages reachable both normally and under
flood. "Person-hours" = one one-way trip per resident (no visit rate applied; see P6).

H1 (concentration): share of total added person-hours from the top 1/5/10 % of villages ranked by
their added person-hours; Gini of village added person-hours.
H2 (bias under flood): overstatement = wmedian(A) / wmedian(B) under flood vs normal; also the
population-weighted mean A-B gap (minutes) among villages reachable under both scenarios.

Writes results/tables/a2_2x2_by_threshold.csv and a2_h1_concentration.csv.
"""
import numpy as np
import pandas as pd

from _common import DATA, TABLES, VID, log_env, wquantile

log_env(__file__)
fl = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))], ignore_index=True)
pop = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "population"])
fl = fl.merge(pop, on=VID, how="left")
fl[["D", "T"]] = fl[["D", "T"]].fillna(0)          # normal rows: D = T = 0 (no closure rule)
assert fl.groupby(["scenario", "event", "D", "T"], dropna=False)[VID].nunique().eq(5159).all()
assert len(fl) == 5159 * 2 * 19

key = ["event", "D", "T"]
norm = fl[fl["event"] == "normal"][[VID, "scenario", "min_any"]].rename(columns={"min_any": "normal"})
fl = fl.merge(norm, on=[VID, "scenario"])
fl["isolated"] = fl["min_any"].isna()
fl["newly_isolated"] = fl["isolated"] & fl["normal"].notna()
both = fl["min_any"].notna() & fl["normal"].notna()
fl["delta_min"] = np.where(both, fl["min_any"] - fl["normal"], np.nan)
fl["added_ph"] = fl["delta_min"] / 60.0 * fl["population"]


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum())) if x.sum() > 0 else np.nan


rows, h1 = [], []
for (ev, D, T, s), g in fl.groupby(key + ["scenario"]):
    tt = g["min_any"].fillna(np.inf)
    w = g["population"]
    r = {"event": ev, "D": D, "T": T, "scenario": s,
         "n_closed_edges": int(g.drop_duplicates("district")["n_closed_edges"].sum()),
         "wmedian_min": wquantile(tt, w, 0.5), "wp90_min": wquantile(tt, w, 0.9),
         "median_min_unw": float(np.median(tt)), "p90_min_unw": float(np.quantile(tt, 0.9)),
         "isolated_villages": int(g["isolated"].sum()), "isolated_pop": float(w[g["isolated"]].sum()),
         "newly_isolated_villages": int(g["newly_isolated"].sum()),
         "newly_isolated_pop": float(w[g["newly_isolated"]].sum()),
         "villages_delayed_gt1min": int((g["delta_min"] > 1).sum()),
         "pop_delayed_gt1min": float(w[g["delta_min"] > 1].sum()),
         "added_person_hours": float(g["added_ph"].sum()),
         "mean_delta_min_popw": float(np.average(g["delta_min"].dropna(), weights=w[g["delta_min"].notna()])),
         "mean_delta_min_unw": float(g["delta_min"].mean())}
    rows.append(r)
    if ev != "normal":
        a = g["added_ph"].fillna(0).clip(lower=0).sort_values(ascending=False).to_numpy()
        tot = a.sum()
        h1.append({"event": ev, "D": D, "T": T, "scenario": s, "total_added_ph": tot,
                   **{f"top{p}pct_share": (a[: max(1, int(round(len(a) * p / 100)))].sum() / tot if tot > 0 else np.nan)
                      for p in (1, 5, 10)},
                   "gini_added_ph": gini(a), "villages_with_added_time": int((a > 0).sum())})

res = pd.DataFrame(rows)
# H2: overstatement under each condition (A vs B, same event/threshold)
wide = res.pivot_table(index=key, columns="scenario", values=["wmedian_min", "wp90_min", "isolated_pop",
                                                              "added_person_hours"])
h2 = pd.DataFrame({"overstatement_wmedian": wide[("wmedian_min", "A")] / wide[("wmedian_min", "B")],
                   "overstatement_wp90": wide[("wp90_min", "A")] / wide[("wp90_min", "B")],
                   "added_ph_A_over_B": wide[("added_person_hours", "A")] / wide[("added_person_hours", "B")],
                   "isolated_pop_A": wide[("isolated_pop", "A")], "isolated_pop_B": wide[("isolated_pop", "B")]})
gap_rows = []
for k, g in fl.groupby(key):
    p = g.pivot_table(index=VID, columns="scenario", values="min_any")
    ok = p.notna().all(axis=1)
    w = pop.set_index(VID).loc[p.index[ok], "population"]
    gap_rows.append({**dict(zip(key, k)),
                     "popw_mean_gap_A_minus_B_min": float(np.average(p.loc[ok, "A"] - p.loc[ok, "B"], weights=w)),
                     "unw_mean_gap_A_minus_B_min": float((p.loc[ok, "A"] - p.loc[ok, "B"]).mean()),
                     "n_reachable_both": int(ok.sum())})
h2 = h2.reset_index().merge(pd.DataFrame(gap_rows), on=key, how="left")

TABLES.mkdir(parents=True, exist_ok=True)
res.to_csv(TABLES / "a2_2x2_by_threshold.csv", index=False)
pd.DataFrame(h1).to_csv(TABLES / "a2_h1_concentration.csv", index=False)
h2.to_csv(TABLES / "a2_h2_bias_under_flood.csv", index=False)
pd.set_option("display.width", 250)
cols = ["event", "D", "T", "scenario", "n_closed_edges", "wmedian_min", "wp90_min", "isolated_villages",
        "isolated_pop", "pop_delayed_gt1min", "added_person_hours"]
print(res[cols].round(2).to_string(index=False))
print("\nH1:\n" + pd.DataFrame(h1).round(3).to_string(index=False))
print("\nH2:\n" + h2.round(3).to_string(index=False))
