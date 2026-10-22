"""A3 step 2: calibrated learned matcher vs the RHAI fuzzy baseline, split by district.

Pair-level classifier: y = 1 for the verified pair of each positive facility; y = 0 for every other
kept candidate of a positive facility and for manually rejected review pairs. Models:
  baseline_rhai  RHAI rule: top-1 = highest token_sort_ratio among LATIN candidates; probability =
                 isotonic calibration of that score (fit out-of-fold)
  logreg         logistic regression on standardised features
  gbm            HistGradientBoosting (shallow)
CV: leave-district-out folds (GroupKFold over districts, 5 folds; never split by row). Out-of-fold
probabilities are isotonic-calibrated within the training folds (nested), so every reported metric is
out-of-district.
Facility-level distribution with an explicit "no match": with calibrated pair probabilities p_c and
an at-most-one-match assumption,
   q_0 ∝ prod_c (1 - p_c),   q_c ∝ p_c prod_{c' != c} (1 - p_c').
Metrics per model, pooled and per district: top-1 / top-5 accuracy on positives; pair-level ECE (10
bins) and Brier; on manually reviewed facilities (accept = 1 / reject = 0) the probability assigned to
the reviewed pair (Brier, AUC) — the one label set not selected by score alone; and agreement with the
50-point satellite validation. Selection bias: positives were found by the fuzzy rule, which favours
fuzzy features in every positive-based metric (stated in outputs).
Final model refit on all labelled data; placement distributions written for all 1,357 facilities
(A4 uses the 741 unlocated).
Writes results/tables/a3_*.csv and data/a3_placement_probs.parquet.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from _common import RHAI, DATA, TABLES, SEED, log_env, set_seeds

set_seeds()
log_env(__file__)
C = pd.read_parquet(DATA / "a3_candidates.parquet")
F = pd.read_parquet(DATA / "a3_facilities.parquet")
dstat = C.groupby("district").agg(d_pool=("entity", "nunique"), d_nonlatin=("script_latin", lambda s: 1 - s.mean()))
C = C.join(dstat, on="district")
C["log_rank_tsr"], C["log_rank_emb"] = np.log(C.rank_tsr), np.log(C.rank_emb)
C["log_same"] = np.log(C.n_same_name)
FEATS = ["fz_tsr", "fz_partial", "fz_wratio", "emb_cos", "log_rank_tsr", "log_rank_emb", "log_same",
         "log_pop", "src_geonames", "script_latin", "n_variants", "d_pool", "d_nonlatin"]
grp = F.set_index("fid")["label_group"]
C["group"] = C["fid"].map(grp)
L = C[(C.group == "positive") | (C.pair_label == "neg_reviewed")].copy()
L["y"] = (L.pair_label == "pos").astype(int)
# a positive facility may match 2 entities within 250 m (duplicates): keep the best-scoring one as y=1
dup = L[L.y == 1].sort_values("fz_tsr", ascending=False).duplicated("fid")
L.loc[dup[dup].index, "y"] = 0
L = L[~((L.y == 0) & L.index.isin(dup[dup].index))]
print(f"labelled pairs {len(L):,} (pos {L.y.sum()}), facilities {L.fid.nunique()}, districts {L.district.nunique()}")


def make(name):
    if name == "logreg":
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                          l2_regularization=1.0, random_state=SEED)


def raw_score(name, train, test):
    if name == "baseline_rhai":
        return train["fz_tsr"].to_numpy(float), test["fz_tsr"].to_numpy(float)
    m = make(name).fit(train[FEATS], train["y"])
    return m.predict_proba(train[FEATS])[:, 1], m.predict_proba(test[FEATS])[:, 1]


def fit_predict(name, train, test):
    """Raw model -> isotonic calibration fitted on inner out-of-fold scores of the training set."""
    inner = GroupKFold(n_splits=4)
    oof = np.zeros(len(train))
    for a, b in inner.split(train, train["y"], train["district"]):
        _, oof[b] = raw_score(name, train.iloc[a], train.iloc[b])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=1 - 1e-4).fit(oof, train["y"])
    _, s_test = raw_score(name, train, test)
    return iso.predict(s_test), iso


def facility_dist(df, p):
    """At-most-one-match distribution per facility: returns q (per pair) and q0 (per facility)."""
    d = df[["fid"]].copy(); d["p"] = np.clip(p, 1e-6, 1 - 1e-6)
    d["l1m"] = np.log1p(-d["p"])
    S = d.groupby("fid")["l1m"].transform("sum")
    w_c = np.exp(np.log(d["p"]) - d["l1m"] + S)          # p_c * prod_{c'!=c}(1-p_c')
    w0 = np.exp(d.groupby("fid")["l1m"].sum())
    Z = w_c.groupby(d["fid"]).sum() + w0
    d["q"] = w_c / d["fid"].map(Z)
    return d["q"].to_numpy(), (w0 / Z)


def ece(p, y, bins=10):
    e = np.clip((p * bins).astype(int), 0, bins - 1)
    return float(sum(abs(p[e == k].mean() - y[e == k].mean()) * (e == k).mean() for k in range(bins) if (e == k).any()))


MODELS = ["baseline_rhai", "logreg", "gbm"]
outer = GroupKFold(n_splits=5)
oof = {m: np.full(len(L), np.nan) for m in MODELS}
fold_of = np.zeros(len(L), int)
for k, (a, b) in enumerate(outer.split(L, L["y"], L["district"])):
    fold_of[b] = k
    tr, te = L.iloc[a], L.iloc[b]
    for m in MODELS:
        te_m = te if m != "baseline_rhai" else te
        oof[m][b], _ = fit_predict(m, tr, te)
    print(f"fold {k}: districts {sorted(te.district.unique())}", flush=True)

rows, per_d = [], []
rev = pd.read_csv(RHAI / "data/pphi_geocode_review_done.csv")
F_rev = F.merge(rev[["district", "name", "decision"]], on=["district", "name"], how="inner")
for m in MODELS:
    d = L.assign(p=oof[m])
    if m == "baseline_rhai":                 # RHAI pool: Latin-script candidates only
        d.loc[d.script_latin == 0, "p"] = 0.0
    q, q0 = facility_dist(d, d["p"].to_numpy())
    d["q"] = q
    d["rk"] = d.groupby("fid")["q"].rank(ascending=False, method="first")
    pos = d[d.fid.map(grp) == "positive"]
    hit = pos[pos.y == 1].set_index("fid")["rk"]
    q0_pos = q0.reindex(hit.index)
    # reviewed facilities: probability on the reviewed pair (accepted pairs are y=1 positives, rejected y=0)
    rv = d[d.fid.isin(F_rev.fid) & ((d.y == 1) | (d.pair_label == "neg_reviewed"))]
    r = {"model": m, "n_pos_fac": len(hit), "top1": (hit <= 1).mean(), "top5": (hit <= 5).mean(),
         "pair_ece": ece(d.p.to_numpy(), d.y.to_numpy()), "pair_brier": brier_score_loss(d.y, d.p),
         "mean_q0_on_positives": float(q0_pos.mean()),
         "reviewed_n": len(rv), "reviewed_brier": brier_score_loss(rv.y, rv.q) if len(rv) else np.nan,
         "reviewed_auc": roc_auc_score(rv.y, rv.q) if rv.y.nunique() == 2 else np.nan}
    rows.append(r)
    for dist_name, g in pos.groupby("district"):
        hd = g[g.y == 1]["rk"]
        per_d.append({"model": m, "district": dist_name, "n_pos_fac": len(hd), "top1": (hd <= 1).mean(),
                      "top5": (hd <= 5).mean(), "pair_ece": ece(g.p.to_numpy(), g.y.to_numpy())})
res = pd.DataFrame(rows)
res_d = pd.DataFrame(per_d).pivot_table(index=["district"], columns="model", values=["n_pos_fac", "top1", "top5", "pair_ece"])
TABLES.mkdir(parents=True, exist_ok=True)
res.to_csv(TABLES / "a3_matcher_overall.csv", index=False)
res_d.to_csv(TABLES / "a3_matcher_by_district.csv")
pd.set_option("display.width", 220)
print("\nOUT-OF-DISTRICT (positives selected by the fuzzy rule -> metrics favour fuzzy features):\n" + res.round(3).to_string(index=False))
print("\nby district:\n" + res_d.round(2).to_string())

# satellite validation: 50 accepted geocodes checked on imagery (verdict yes/no/unclear)
sat = pd.read_csv(RHAI / "data/geocode_satellite_validation.csv")
sv = sat.merge(F[["fid", "name", "district"]], on=["name", "district"], how="left")
best = max(MODELS[1:], key=lambda m: -res.set_index("model").loc[m, "pair_brier"])
dB = L.assign(p=oof[best]); dB["q"], _ = facility_dist(dB, dB.p.to_numpy())
qpos = dB[dB.y == 1].set_index("fid")["q"]
sv["q_model"] = sv.fid.map(qpos)
sv_s = sv.groupby("verdict")["q_model"].agg(["size", "mean", "median"])
sv_s.to_csv(TABLES / "a3_satellite_check.csv")
print(f"\nsatellite validation vs {best} out-of-fold q of the accepted pair:\n" + sv_s.round(3).to_string())

# final fit on all labelled pairs, predict all candidates -------------------------------
p_all, iso = fit_predict(best, L, C)
C["p"] = p_all
C["q"], q0_all = facility_dist(C, C.p.to_numpy())
C["q0"] = C.fid.map(q0_all)
C["model"] = best
C.to_parquet(DATA / "a3_placement_probs.parquet", index=False)
U = C[C.group != "positive"]
fq0 = U.groupby("fid")["q0"].first()
top = U.sort_values("q", ascending=False).drop_duplicates("fid")
print(f"\nchosen model: {best}. Unlocated facilities with candidates: {fq0.size} "
      f"(+{(F.label_group != 'positive').sum() - fq0.size} without any candidate)")
print("P(no match) among unlocated: " + fq0.describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())
print(f"unlocated whose top candidate has q >= 0.5: {(top.q >= 0.5).sum()} "
      f"(of which non-Latin top candidate: {((top.q >= 0.5) & (top.script_latin == 0)).sum()})")
by = U.groupby("district").agg(fac=("fid", "nunique")).join(fq0.groupby(U.drop_duplicates("fid").set_index("fid")["district"]).mean().rename("mean_q0"))
by.to_csv(TABLES / "a3_unlocated_by_district.csv")
print(by.sort_values("mean_q0").round(3).to_string())
