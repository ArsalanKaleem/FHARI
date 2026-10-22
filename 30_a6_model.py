"""A6: edge-level closure-exposure predictor, trained on 2022, tested on 2025 (transfer across flood types).

Pre-registered framing (decision_log 2026-10-20 / -22): target = segment closure EXPOSURE under the base
rule (v1, D3, T0.6), not observed closure; threshold for testing H4 met (2025: 2,026 positive segments in
7 districts with >= 20). 2025 was mainly riverine (Indus channel), 2022 widespread rain-driven flooding.
Models (hyper-parameters fixed before any fit):
  gbm        HistGradientBoosting (max_leaf_nodes 31, learning_rate 0.05, max_iter 300, l2 1.0, no early
             stopping, road class categorical, seed 20221001) on all features
  base_river logistic regression on log(dist_river_km + 0.01)
  base_fac   logistic regression on log(dist_facility_km + 0.01)
Evaluation:
  (1) 2022 leave-one-district-out CV, pooled out-of-fold predictions
  (2) out-of-event: fit on all 2022, predict 2025
  each for the full set and the sensitivity excluding Khairpur, Sukkur, Ghotki (train and test).
Metrics: AUC-PR (average precision) with lift over prevalence, ROC AUC, Brier, ECE (10 quantile bins);
95 % intervals from a district-cluster bootstrap (500 resamples). SHAP (TreeExplainer) on a seeded sample of 20,000
2025 segments for the out-of-event gbm.
Writes results/tables/a6_metrics.csv, a6_calibration.csv, a6_shap.csv, a6_2025_isolation_descriptive.csv.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from _common import DATA, TABLES, VID, SEED, log_env, set_seeds

set_seeds(); log_env(__file__)
S = pd.read_parquet(DATA / "a6_segments.parquet")
S["hw"] = S["highway"].astype("category").cat.codes
FEATS = ["elevation_m", "slope_deg", "twi", "dist_river_km", "dist_canal_km", "hw", "length_m", "dist_facility_km", "pop_1km"]
FRINGE = {"Khairpur", "Sukkur", "Ghotki"}
rng = np.random.default_rng(SEED)
N_BOOT = 500        # district-cluster bootstrap resamples (AUC-PR over ~547 k segments is costly)


def make(name):
    if name == "gbm":
        return HistGradientBoostingClassifier(max_leaf_nodes=31, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                                              early_stopping=False, categorical_features=[FEATS.index("hw")],
                                              random_state=SEED)
    return LogisticRegression(max_iter=1000)


def X(df, name):
    if name == "gbm":
        return df[FEATS]
    c = "dist_river_km" if name == "base_river" else "dist_facility_km"
    return np.log(df[[c]] + 0.01)


def ece(p, y, bins=10):
    q = pd.qcut(p, bins, labels=False, duplicates="drop")
    d = pd.DataFrame({"p": p, "y": y, "q": q})
    g = d.groupby("q").agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    return float((abs(g.p - g.y) * g.n).sum() / g.n.sum()), g


def metrics(y, p, dist):
    ap = average_precision_score(y, p)
    out = {"n": len(y), "positives": int(y.sum()), "prevalence": float(y.mean()), "auc_pr": ap,
           "auc_pr_lift": ap / y.mean(), "roc_auc": roc_auc_score(y, p), "brier": brier_score_loss(y, p),
           "ece": ece(p, y)[0]}
    ds = np.unique(dist); idx = {d: np.nonzero(dist == d)[0] for d in ds}
    boot = []
    for _ in range(N_BOOT):
        pick = np.concatenate([idx[d] for d in rng.choice(ds, len(ds), replace=True)])
        if y[pick].sum() == 0:
            continue
        boot.append(average_precision_score(y[pick], p[pick]))
    out["auc_pr_lo95"], out["auc_pr_hi95"] = np.percentile(boot, [2.5, 97.5])
    return out


rows, cal = [], []
for subset in ("all", "excl_fringe"):
    D = S if subset == "all" else S[~S.district.isin(FRINGE)]
    y22, y25, dist = D.y2022.to_numpy(int), D.y2025.to_numpy(int), D.district.to_numpy()
    for name in ("gbm", "base_river", "base_fac"):
        oof = np.zeros(len(D))
        for d in np.unique(dist):                                  # leave-one-district-out
            tr, te = dist != d, dist == d
            if y22[tr].sum() == 0:
                continue
            m = make(name).fit(X(D[tr], name), y22[tr])
            oof[te] = m.predict_proba(X(D[te], name))[:, 1]
        rows.append({"subset": subset, "eval": "2022_LODO_CV", "model": name, **metrics(y22, oof, dist)})
        m = make(name).fit(X(D, name), y22)
        p25 = m.predict_proba(X(D, name))[:, 1]
        rows.append({"subset": subset, "eval": "2025_out_of_event", "model": name, **metrics(y25, p25, dist)})
        for ev, p, y in (("2022_LODO_CV", oof, y22), ("2025_out_of_event", p25, y25)):
            g = ece(p, y)[1].reset_index(); g["subset"], g["eval"], g["model"] = subset, ev, name
            cal.append(g)
        if name == "gbm" and subset == "all":
            import shap
            samp = D.sample(20000, random_state=SEED)
            sv = shap.TreeExplainer(m).shap_values(samp[FEATS])
            sv = sv[1] if isinstance(sv, list) else sv
            shp = pd.DataFrame({"feature": FEATS, "mean_abs_shap": np.abs(sv).mean(axis=0),
                                "corr_feature_shap": [np.corrcoef(samp[f].astype(float), sv[:, i])[0, 1] for i, f in enumerate(FEATS)]})
            shp.sort_values("mean_abs_shap", ascending=False).to_csv(TABLES / "a6_shap.csv", index=False)
        print(f"{subset:12s} {name:10s} done", flush=True)

M = pd.DataFrame(rows); M.to_csv(TABLES / "a6_metrics.csv", index=False)
pd.concat(cal).to_csv(TABLES / "a6_calibration.csv", index=False)

# descriptive 2025 village isolation (A2, v1, base, 1 km rule)
f = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))])
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "pop_part2km"])
b = f[(f.event == "2025") & (f.D == 3) & (f["T"] == 0.6)]
nm = f[f.event == "normal"][[VID, "scenario", "min_any_r1000"]].rename(columns={"min_any_r1000": "normal"})
b = b.merge(nm, on=[VID, "scenario"]).merge(pop, on=VID)
iso = b[b.min_any_r1000.isna() & ~b.no_road_r1000 & b.normal.notna()][[VID, "district", "scenario", "pop_part2km"]]
iso.to_csv(TABLES / "a6_2025_isolation_descriptive.csv", index=False)
pd.set_option("display.width", 220)
print("\n" + M.round(4).to_string(index=False))
print("\nSHAP (2025, gbm trained on 2022):\n" + pd.read_csv(TABLES / "a6_shap.csv").round(4).to_string(index=False))
print("\n2025 newly isolated villages (1 km rule), by scenario:\n" + iso.groupby(["scenario", "district"]).agg(
    villages=(VID, "size"), people_dedup=("pop_part2km", "sum")).round(0).to_string())
