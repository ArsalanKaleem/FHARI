"""A8 audit: every number used in the manuscript, recomputed from results tables / data (never typed).

Each number has a key (referenced in docs/manuscript_skeleton.md as {{key}}) and its source. Writes
results/paper_a_numbers.txt (human-readable, grouped by section) and results/paper_a_numbers.json.
Anything in the manuscript that is not produced here is unverified.
"""
import json

import numpy as np
import pandas as pd

from _common import DATA, TABLES, PAPER, VID, log_env

log_env(__file__)
N, SRC = {}, {}


def put(key, val, src, fmt="{:,.4g}"):
    N[key] = (float(val) if isinstance(val, (int, float, np.integer, np.floating)) else val)
    SRC[key] = (src, fmt)


t = lambda f: pd.read_csv(TABLES / f)
BASE = "2022_D3_T0.6_N200_K50"

# ---- data ---------------------------------------------------------------------------------
vm = pd.read_parquet(DATA / "village_master.parquet")
put("data.villages", len(vm), "village_master.parquet", "{:,.0f}")
put("data.districts_with_villages", vm.district.nunique(), "village_master.parquet", "{:,.0f}")
c3 = t("check3_population.csv").set_index("metric")["value"]
put("data.pop_dedup_within_2km_M", c3["pop_within_2km_of_any_village (deduplicated)"] / 1e6, "check3_population.csv", "{:.1f}")
put("data.double_count_factor", c3["double_count_factor = buffer_sum / dedup_covered"], "check3_population.csv", "{:.2f}")
put("data.worldpop_sindh_M", c3["raster_total_pop"] / 1e6, "check3_population.csv", "{:.1f}")
cats = t("a2_masks_categories.csv")
b = cats[(cats["mask"] == "v1") & (cats.r == 1000) & (cats.event == 2022) & (cats.D == 3) & (cats["T"] == 0.6)].set_index("scenario")
put("data.no_road_villages", b.loc["B", "no_road_villages"], "a2_masks_categories.csv", "{:,.0f}")
put("data.no_road_people", b.loc["B", "no_road_people_dedup"], "a2_masks_categories.csv", "{:,.0f}")

import geopandas as gpd
from _common import RHAI
put("data.facilities_A", len(gpd.read_file(RHAI / "data/facilities_tiered.gpkg")), "RHAI facilities_tiered.gpkg", "{:,.0f}")
put("data.facilities_B", len(gpd.read_file(RHAI / "data/facilities_merged_final.gpkg")), "RHAI facilities_merged_final.gpkg", "{:,.0f}")
put("data.pphi_register", len(pd.read_csv(RHAI / "data/pphi_facilities.csv")), "RHAI pphi_facilities.csv", "{:,.0f}")
put("data.pphi_geocoded", len(gpd.read_file(RHAI / "data/pphi_geocoded_reviewed.gpkg")), "RHAI pphi_geocoded_reviewed.gpkg", "{:,.0f}")
sat = pd.read_csv(RHAI / "data/geocode_satellite_validation.csv")
put("data.pphi_sat_correct_share", (sat.verdict == "yes").mean(), "RHAI geocode_satellite_validation.csv", "{:.0%}")
put("data.pphi_sat_n", len(sat), "RHAI geocode_satellite_validation.csv", "{:,.0f}")
CL = [76, 77, 78] + list(range(2294, 2305))
dch = pd.read_csv(TABLES / "a2_scenarioA_paperA_vs_rhai_villages.csv")
dcl = dch[dch[VID].isin(CL)]["min_any_diff"].dropna()
put("rhai.dadu_cluster_villages", len(CL), "fixed id list (76-78, 2294-2304)", "{:,.0f}")
put("rhai.dadu_cluster_diff_min", dcl.min(), "a2_scenarioA_paperA_vs_rhai_villages.csv", "{:.0f}")
put("rhai.dadu_cluster_diff_max", dcl.max(), "a2_scenarioA_paperA_vs_rhai_villages.csv", "{:.0f}")

# ---- RHAI reproduction / shared graph --------------------------------------------------------
hc = t("a0_headline_check.csv").set_index("metric")["value"]
put("rhai.wmedian_A", hc["rhai_method_wmedian_A_min"], "a0_headline_check.csv", "{:.2f}")
put("rhai.wmedian_B", hc["rhai_method_wmedian_B_min"], "a0_headline_check.csv", "{:.2f}")
put("rhai.overstatement", hc["rhai_method_overstatement_x"], "a0_headline_check.csv", "{:.2f}")
sg = t("a2_same_graph_vs_rhai.csv").set_index("metric")["value"]
put("rhai.same_graph_overstatement", sg["same: overstatement x"], "a2_same_graph_vs_rhai.csv", "{:.2f}")
put("rhai.slower_under_B_rhai", sg["rhai: villages slower under B (>0.01)"], "a2_same_graph_vs_rhai.csv", "{:,.0f}")
put("rhai.slower_under_B_same", sg["same: villages slower under B (>0.01)"], "a2_same_graph_vs_rhai.csv", "{:,.0f}")
put("rhai.A_villages_changed", sg["A: villages differing >1e-6 min"], "a2_same_graph_vs_rhai.csv", "{:,.0f}")
put("rhai.A_max_change_min", sg["A: max |diff| min"], "a2_same_graph_vs_rhai.csv", "{:.1f}")

# ---- flood masks ------------------------------------------------------------------------------
ag = t("a1_agreement_overall.csv").set_index(t("a1_agreement_overall.csv").columns[0])["value"]
put("a1.cropland_kappa", ag["cohen_kappa"], "a1_agreement_overall.csv", "{:.4f}")
dw = t("check5_dw_validation.csv")
aw = dw[dw.subset == "area-weighted"].iloc[0]
put("a1.dw_kappa", aw.kappa, "check5_dw_validation.csv", "{:.2f}")
put("a1.dw_precision", aw.precision, "check5_dw_validation.csv", "{:.2f}")
put("a1.dw_recall", aw.recall, "check5_dw_validation.csv", "{:.2f}")
vv = t("a1_v2_validation.csv").set_index(["mask", "subset"])
for m in ("v1", "v2"):
    put(f"a1.{m}_fringe_precision", vv.loc[(m, "fringe"), "precision"], "a1_v2_validation.csv", "{:.3f}")
    put(f"a1.{m}_core_recall", vv.loc[(m, "core"), "recall"], "a1_v2_validation.csv", "{:.3f}")
put("a1.v2_success", str(bool(t("a1_v2_verdict.csv").set_index(t("a1_v2_verdict.csv").columns[0]).loc["v2", "SUCCESS"])), "a1_v2_verdict.csv", "{}")

# ---- A2 categories, H1, H2 -----------------------------------------------------------------------
for s in ("A", "B"):
    put(f"a2.newly_isolated_villages_{s}", b.loc[s, "newly_isolated_villages"], "a2_masks_categories.csv", "{:,.0f}")
    put(f"a2.newly_isolated_people_{s}", b.loc[s, "newly_isolated_people_dedup"], "a2_masks_categories.csv", "{:,.0f}")
    put(f"a2.delayed_people_{s}", b.loc[s, "delayed_people_dedup"], "a2_masks_categories.csv", "{:,.0f}")
hh = t("a2_masks_h1h2.csv")
hb = hh[(hh["mask"] == "v1") & (hh.r == 1000) & (hh.event == 2022) & (hh.D == 3) & (hh["T"] == 0.6)].set_index("scenario")
put("a2.h1_top10_share_B", hb.loc["B", "top10_share"], "a2_masks_h1h2.csv", "{:.2f}")
put("a2.h1_gini_villages_B", hb.loc["B", "gini_villages"], "a2_masks_h1h2.csv", "{:.2f}")
bt = t("a2_masks_h2_bootstrap.csv")
for met in ("ratio_added_ph", "ratio_newly_isolated", "ratio_cov60_shortfall", "ratio_wmedian"):
    put(f"h2.{met}_2022", hb.loc["A", met], "a2_masks_h1h2.csv", "{:.2f}")
    r = bt[(bt["mask"] == "v1") & (bt.event == 2022) & (bt.metric == met)].iloc[0]
    put(f"h2.{met}_2022_lo", r.lo95, "a2_masks_h2_bootstrap.csv", "{:.2f}")
    put(f"h2.{met}_2022_hi", r.hi95, "a2_masks_h2_bootstrap.csv", "{:.2f}")
h2c = t("a7_h2_by_config.csv")
for o in ("cov60_shortfall", "isolated_dedup", "added_ph_dedup"):
    v = h2c[h2c.outcome == o]["ratio_A_B"]
    put(f"h2.range_{o}_min", v.min(), "a7_h2_by_config.csv", "{:.2f}"); put(f"h2.range_{o}_max", v.max(), "a7_h2_by_config.csv", "{:.2f}")

# ---- A3 / A4 ----------------------------------------------------------------------------------
m3 = t("a3_matcher_overall.csv").set_index("model")
for k in ("baseline_rhai", "gbm"):
    put(f"a3.top1_{k}", m3.loc[k, "top1"], "a3_matcher_overall.csv", "{:.3f}")
    put(f"a3.reviewed_brier_{k}", m3.loc[k, "reviewed_brier"], "a3_matcher_overall.csv", "{:.3f}")
    put(f"a3.reviewed_auc_{k}", m3.loc[k, "reviewed_auc"], "a3_matcher_overall.csv", "{:.3f}")
P = pd.read_parquet(DATA / "a3_placement_probs.parquet")
F = pd.read_parquet(DATA / "a3_facilities.parquet")
q0 = P[P.fid.isin(F[F.label_group != "positive"].fid)].groupby("fid").q0.first()
put("a3.unlocated", (F.label_group != "positive").sum(), "a3_facilities.parquet", "{:,.0f}")
put("a3.median_p_nomatch", q0.median(), "a3_placement_probs.parquet", "{:.2f}")
PL = pd.read_parquet(DATA / "a4/base/placements.parquet")
put("a4.placed_per_draw", (PL.outcome == "placed").groupby(PL["draw"]).sum().mean(), "a4/base/placements.parquet", "{:.0f}")
ps = pd.read_csv(TABLES / "a4_province_summary.csv", index_col=0)
lay = t("a4_layers_AB_same_defs.csv").set_index("layer")
put("a4.wmedian_ens", ps.loc["base", "wmedian_normal_mean"], "a4_province_summary.csv", "{:.2f}")
put("a4.wmedian_ens_lo", ps.loc["base", "wmedian_normal_lo95"], "a4_province_summary.csv", "{:.2f}")
put("a4.wmedian_ens_hi", ps.loc["base", "wmedian_normal_hi95"], "a4_province_summary.csv", "{:.2f}")
put("a4.overstatement_A_vs_ens", lay.loc["A", "wmedian_normal"] / ps.loc["base", "wmedian_normal_mean"], "a4 tables", "{:.2f}")
put("a4.overstatement_B_vs_ens", lay.loc["B", "wmedian_normal"] / ps.loc["base", "wmedian_normal_mean"], "a4 tables", "{:.2f}")

# ---- A7 ---------------------------------------------------------------------------------------
R = t(f"a7_{BASE}_regret.csv")
for obj in ("cov60", "iso", "ph"):
    for a in ("A", "B", "ens"):
        r = R[(R.objective == obj) & (R.K == 20) & (R.alloc == a)].iloc[0]
        put(f"a7.regret_{a}_{obj}_K20", r.regret_share, f"a7_{BASE}_regret.csv", "{:.3f}")
        put(f"a7.regret_{a}_{obj}_K20_lo", r.regret_lo95, f"a7_{BASE}_regret.csv", "{:.3f}")
        put(f"a7.regret_{a}_{obj}_K20_hi", r.regret_hi95, f"a7_{BASE}_regret.csv", "{:.3f}")
        put(f"a7.absregret_{a}_{obj}_K20", r.abs_regret_mean, f"a7_{BASE}_regret.csv", "{:,.0f}")
    put(f"a7.achievable_{obj}_K20", R[(R.objective == obj) & (R.K == 20) & (R.alloc == "A")].iloc[0].achievable_abs_mean,
        f"a7_{BASE}_regret.csv", "{:,.0f}")
e = R[(R.objective == "cov60") & (R.K == 20) & (R.alloc == "EVPI")].iloc[0]
put("a7.evpi_cov60_K20", e.abs_regret_mean, f"a7_{BASE}_regret.csv", "{:,.1f}")
put("a7.evpi_cov60_K20_hi", e.abs_regret_hi95, f"a7_{BASE}_regret.csv", "{:,.1f}")
evv = t(f"a7_{BASE}_evppi_validation.csv").iloc[0]
put("a7.evpi_additive_K20", evv.evpi_additive_dedup, f"a7_{BASE}_evppi_validation.csv", "{:,.0f}")
J = t(f"a7_{BASE}_jaccard.csv"); j = J[(J.objective == "cov60") & (J.K == 20)].iloc[0]
put("a7.jaccard_A_ens_K20", j.J_A_ens, f"a7_{BASE}_jaccard.csv", "{:.2f}"); put("a7.jaccard_B_ens_K20", j.J_B_ens, f"a7_{BASE}_jaccard.csv", "{:.2f}")
SX = t("a7_sensitivity_regret.csv")
sa = SX[(SX.objective == "cov60") & (SX.alloc == "A") & (SX.K.astype(str).isin(["20", "length"]))]["regret_share"]
put("a7.sens_regret_A_cov60_min", sa.min(), "a7_sensitivity_regret.csv", "{:.3f}"); put("a7.sens_regret_A_cov60_max", sa.max(), "a7_sensitivity_regret.csv", "{:.3f}")
si = SX[(SX.objective == "iso") & (SX.alloc == "A") & (SX.K.astype(str).isin(["20", "length"]))]["regret_share"]
put("a7.sens_regret_A_iso_max", si.max(), "a7_sensitivity_regret.csv", "{:.3f}")
sb = SX[(SX.objective == "cov60") & (SX.alloc == "B") & (SX.K.astype(str).isin(["20", "length"]))]["regret_share"]
put("a7.sens_regret_B_cov60_max", sb.max(), "a7_sensitivity_regret.csv", "{:.3f}")

# ---- A6 ---------------------------------------------------------------------------------------
M = t("a6_metrics.csv").set_index(["subset", "eval", "model"])
for sub in ("all", "excl_fringe"):
    for ev in ("2022_LODO_CV", "2025_out_of_event"):
        for mdl in ("gbm", "base_fac", "base_river"):
            r = M.loc[(sub, ev, mdl)]
            k = f"a6.{sub}.{ev}.{mdl}"
            put(k + ".aucpr", r.auc_pr, "a6_metrics.csv", "{:.3f}")
            put(k + ".lo", r.auc_pr_lo95, "a6_metrics.csv", "{:.3f}"); put(k + ".hi", r.auc_pr_hi95, "a6_metrics.csv", "{:.3f}")
        put(f"a6.{sub}.{ev}.prevalence", M.loc[(sub, ev, "gbm")].prevalence, "a6_metrics.csv", "{:.4f}")
sh = t("a6_shap.csv").iloc[0]
put("a6.top_shap_feature", sh.feature, "a6_shap.csv", "{}")

# ---- additional keys used by the full manuscript (36_paper_text.py) -------------------------
put("a1.cropland_cells", ag["n_cells"], "a1_agreement_overall.csv", "{:,.0f}")
put("a1.v1_core_precision", vv.loc[("v1", "core"), "precision"], "a1_v2_validation.csv", "{:.2f}")
x22 = t("a2_2x2_by_threshold.csv")
for ev in ("2022", "2025"):
    r = x22[(x22.event.astype(str) == ev) & (x22.D == 3) & (x22["T"] == 0.6) & (x22.scenario == "B")].iloc[0]
    put(f"a2.closed_edges_{ev}", r.n_closed_edges, "a2_2x2_by_threshold.csv", "{:,.0f}")
for ev, suf in ((2022, ""), (2025, "_2025")):
    bb = cats[(cats["mask"] == "v1") & (cats.r == 1000) & (cats.event == ev) & (cats.D == 3) & (cats["T"] == 0.6)].set_index("scenario")
    for s in ("A", "B"):
        put(f"a2.newly_isolated_villages_{s}{suf}", bb.loc[s, "newly_isolated_villages"], "a2_masks_categories.csv", "{:,.0f}")
        put(f"a2.newly_isolated_people_{s}{suf}", bb.loc[s, "newly_isolated_people_dedup"], "a2_masks_categories.csv", "{:,.0f}")
        put(f"a2.delayed_villages_{s}{suf}", bb.loc[s, "delayed_villages"], "a2_masks_categories.csv", "{:,.0f}")
        put(f"a2.delayed_people_{s}{suf}", bb.loc[s, "delayed_people_dedup"], "a2_masks_categories.csv", "{:,.0f}")
for r_ in (500, 2000):
    bb = cats[(cats["mask"] == "v1") & (cats.r == r_) & (cats.event == 2022) & (cats.D == 3) & (cats["T"] == 0.6) & (cats.scenario == "B")].iloc[0]
    put(f"a2.iso_r{r_}_B", bb.newly_isolated_villages, "a2_masks_categories.csv", "{:,.0f}")
hb25 = hh[(hh["mask"] == "v1") & (hh.r == 1000) & (hh.event == 2025) & (hh.D == 3) & (hh["T"] == 0.6)].set_index("scenario")
put("h2.ratio_added_ph_2025", hb25.loc["A", "ratio_added_ph"], "a2_masks_h1h2.csv", "{:.2f}")
put("h2.ratio_cov60_shortfall_2025", hb25.loc["A", "ratio_cov60_shortfall"], "a2_masks_h1h2.csv", "{:.1f}")
put("h2.ratio_newly_isolated_2025", hb25.loc["A", "ratio_newly_isolated"], "a2_masks_h1h2.csv", "{:.2f}")
put("a3.rejected", (F.label_group == "rejected").sum(), "a3_facilities.parquet", "{:,.0f}")
put("a4.wmedian_q05", ps.loc["q0x0.5", "wmedian_normal_mean"], "a4_province_summary.csv", "{:.2f}")
put("a4.wmedian_q2", ps.loc["q0x2", "wmedian_normal_mean"], "a4_province_summary.csv", "{:.2f}")
try:
    seg = pd.read_parquet(DATA / "a6_segments.parquet", columns=["district", "y2025"])
    pos25, nseg = seg.groupby("district").y2025.sum(), len(seg)
except FileNotFoundError:       # repository copy: the 40 MB segment table is not versioned
    sc = t("a6_segment_counts.csv").set_index("district")
    pos25, nseg = sc["pos_2025"], int(sc["segments"].sum())
put("a6.segments", nseg, "a6_segments.parquet / a6_segment_counts.csv", "{:,.0f}")
put("a6.positives_2025", pos25.sum(), "a6_segments.parquet", "{:,.0f}")
put("a6.districts_ge20_2025", (pos25 >= 20).sum(), "a6_segments.parquet", "{:,.0f}")
put("a6.top_shap_label", {"pop_1km": "population within about 1 km"}.get(sh.feature, sh.feature), "a6_shap.csv", "{}")
put("a7.evpi_additive_ratio", evv.evpi_additive_dedup / evv.evpi_exact_dedup, f"a7_{BASE}_evppi_validation.csv", "{:.0f}")
for k in (5, 50):
    put(f"a7.regret_A_cov60_K{k}", R[(R.objective == "cov60") & (R.K == k) & (R.alloc == "A")].iloc[0].regret_share,
        f"a7_{BASE}_regret.csv", "{:.3f}")
reg = lambda cfg: SX[(SX.cfg == cfg) & (SX.objective == "cov60") & (SX.alloc == "A") & (SX.K.astype(str) == "20")].regret_share.iloc[0]
put("a7.regret_A_cov60_emb", reg("2022_D3_T0.6_emb_N200_K50"), "a7_sensitivity_regret.csv", "{:.3f}")
put("a7.regret_A_cov60_2025", reg("2025_D3_T0.6_N200_K50"), "a7_sensitivity_regret.csv", "{:.3f}")
put("a7.regret_A_cov60_K20_pct", N["a7.regret_A_cov60_K20"] * 100, f"a7_{BASE}_regret.csv", "{:.0f} %")
put("a7.sens_regret_A_cov60_min_pct", sa.min() * 100, "a7_sensitivity_regret.csv", "{:.0f}")
put("a7.sens_regret_A_cov60_max_pct", sa.max() * 100, "a7_sensitivity_regret.csv", "{:.0f} %")

# ---- write --------------------------------------------------------------------------------
lines = ["Paper A — every number used in the manuscript (regenerate with 32_audit_numbers.py).",
         "Anything in the text not listed here is UNVERIFIED.", ""]
cur = None
for k in N:
    sec = k.split(".")[0]
    if sec != cur:
        lines += ["", f"[{sec}]"]; cur = sec
    src, fmt = SRC[k]
    v = N[k]
    lines.append(f"  {k:48s} {fmt.format(v) if not isinstance(v, str) else v:>14s}   <- {src}")
(PAPER / "results" / "paper_a_numbers.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
(PAPER / "results" / "paper_a_numbers.json").write_text(json.dumps(
    {k: {"value": N[k], "display": (SRC[k][1].format(N[k]) if not isinstance(N[k], str) else N[k]), "source": SRC[k][0]} for k in N},
    indent=1), encoding="utf-8")
print("\n".join(lines))
