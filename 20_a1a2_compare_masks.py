"""v1 vs v2 flood mask: pre-registered validation test, then H1/H2 under decision-6 categories.

Part 1 — pre-registered success criterion (decision_log 2026-10-20): on the identical 2,100-point
Dynamic World sample, compare v1 (fd >= 3) with v2 (fd >= 3 and not dry-season persistent), and the
v2s25 sensitivity. Desert fringe = Khairpur, Sukkur, Ghotki; core = Dadu, Larkana, Jakobabad.
Success = fringe precision >= 0.40 AND +0.25 vs v1; core precision and recall each >= v1 - 0.02.

Part 2 — categories at radius r (base r = 1 km; 0.5 and 2 km sensitivity), mutually exclusive:
  no_road            no road node within r
  isolated_baseline  road within r, unreachable even on normal roads
  newly_isolated     reachable normally, unreachable under flood
  delayed            flood time (best node within r) exceeds normal by > 0.01 min
  unaffected
Weights: shares/ratios = RHAI 2 km buffer population; absolute people and person-hours = deduplicated
2 km partition ("people within 2 km of a mapped village").
H1: top-10 % share of added person-hours among delayed villages, Gini (villages, people).
H2: A/B ratios of flood wmedian time, added person-hours, newly isolated population, and the
coverage shortfall (share NOT within 60 min under flood, road villages); 95 % village bootstrap
stratified by district (2,000 resamples) for the base configurations (2022 and 2025, D3, T0.6, r 1 km).
Writes results/tables/a1_v2_validation.csv, a2_masks_categories.csv, a2_masks_h1h2.csv.
"""
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio

from _common import DATA, TABLES, VID, SEED, log_env, wquantile
import _routing as R

log_env(__file__)
MASKS = [m for m in ("v1", "v2", "v2s25") if (DATA / ("a2_flood" if m == "v1" else f"a2_flood_{m}")).exists()]
FRINGE, CORE = {"Khairpur", "Sukkur", "Ghotki"}, {"Dadu", "Larkana", "Jakobabad"}

# ---- part 1: validation ---------------------------------------------------------------
HAVE_DRY = (DATA / "raw/s1_flood/s1_dry_2022_30m.tif").exists()
if not HAVE_DRY:
    print("dry-season raster not downloaded yet: skipping the v2 validation test (part 1)")
if HAVE_DRY:
    p = pd.read_csv(DATA / "check5_dw_samples.csv")
    g = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p.x, p.y), crs=32642)
    g = gpd.sjoin(g, R.districts().to_crs(32642), how="left", predicate="within")
    pers = {}
    with rasterio.open(DATA / "raw/s1_flood/s1_dry_2022_30m.tif") as r:
        vals = np.array(list(r.sample(zip(g.x, g.y))))
    dfd, dob = vals[:, 0].astype(float), vals[:, 1].astype(float)
    for m, thr in (("v1", None), ("v2", 0.5), ("v2s25", 0.25)):
        pers[m] = np.zeros(len(g), bool) if thr is None else (dob >= 5) & (dfd >= thr * np.maximum(dob, 1))
    ok = g.dw_obs.fillna(0) >= 3
    ref = (g.dw_wet / g.dw_obs) >= 0.5
    vrows = []
    for m in pers:
        s1 = (g.fd >= 3) & ~pers[m]
        for name, sel in (("fringe", g.district.isin(FRINGE)), ("core", g.district.isin(CORE)), ("all", pd.Series(True, index=g.index))):
            d = ok & sel
            tp = (s1 & ref & d).sum(); fp = (s1 & ~ref & d).sum(); fn = (~s1 & ref & d).sum()
            vrows.append({"mask": m, "subset": name, "n": int(d.sum()), "s1_flooded": int((s1 & d).sum()),
                          "precision": tp / (tp + fp) if tp + fp else np.nan, "recall": tp / (tp + fn) if tp + fn else np.nan,
                          "points_masked_dry": int((pers[m] & d).sum())})
    val = pd.DataFrame(vrows)
    v = val.set_index(["mask", "subset"])
    verdict = {}
    for m in [x for x in pers if x != "v1"]:
        a = v.loc[(m, "fringe"), "precision"] >= 0.40 and v.loc[(m, "fringe"), "precision"] - v.loc[("v1", "fringe"), "precision"] >= 0.25
        b = all(v.loc[(m, "core"), k] >= v.loc[("v1", "core"), k] - 0.02 for k in ("precision", "recall"))
        verdict[m] = {"criterion_a_fringe": bool(a), "criterion_b_core": bool(b), "SUCCESS": bool(a and b)}
    val.to_csv(TABLES / "a1_v2_validation.csv", index=False)
    pd.DataFrame(verdict).T.to_csv(TABLES / "a1_v2_verdict.csv")
    print("PRE-REGISTERED VALIDATION TEST\n" + val.round(3).to_string(index=False))
    print("verdict:", verdict)

# ---- part 2: categories, H1, H2 ----------------------------------------------------------
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "population", "pop_part2km"])


def load(mask):
    d = DATA / ("a2_flood" if mask == "v1" else f"a2_flood_{mask}")
    f = pd.concat([pd.read_parquet(x) for x in sorted(d.glob("*.parquet"))], ignore_index=True).merge(pop, on=VID)
    f[["D", "T"]] = f[["D", "T"]].fillna(0)
    return f


def categorise(f, r):
    t = f"min_any_r{r}" if r else "min_any"
    nr = f[f"no_road_r{r}"] if r else pd.Series(False, index=f.index)
    norm = f[f.event == "normal"][[VID, "scenario", t]].rename(columns={t: "normal_t"})
    x = f[f.event != "normal"].merge(norm, on=[VID, "scenario"])
    nrx = x[f"no_road_r{r}"] if r else pd.Series(False, index=x.index)
    delta = x[t] - x["normal_t"]
    x["cat"] = np.select([nrx, x.normal_t.isna(), x[t].isna(), delta > 0.01],
                         ["no_road", "isolated_baseline", "newly_isolated", "delayed"], "unaffected")
    x["t_flood"], x["delta"] = x[t], np.where(x.cat == "delayed", delta, 0.0)
    return x


def gini(x, w=None):
    x = np.asarray(x, float); w = np.ones_like(x) if w is None else np.asarray(w, float)
    o = np.argsort(x); x, w = x[o], w[o]; cw = np.cumsum(w); cxw = np.cumsum(x * w)
    if len(x) < 2 or cxw[-1] <= 0:
        return np.nan
    L = np.r_[0, cxw / cxw[-1]]; P = np.r_[0, cw / cw[-1]]
    return float(1 - np.sum((P[1:] - P[:-1]) * (L[1:] + L[:-1])))


def stats(g):
    road = g.cat != "no_road"
    tt = g.loc[road, "t_flood"].fillna(np.inf)
    dl = g[g.cat == "delayed"]
    ph = dl["delta"] / 60 * dl["population"]
    phs = np.sort(ph.to_numpy())[::-1]; k = max(1, int(np.ceil(0.1 * len(phs)))) if len(phs) else 0
    return {"wmedian_flood_min": wquantile(tt, g.loc[road, "population"], 0.5) if road.any() else np.nan,
            "added_ph_dedup": float((dl["delta"] / 60 * dl["pop_part2km"]).sum()),
            "added_ph_rhai": float(ph.sum()),
            "newly_isolated_pop_rhai": float(g.loc[g.cat == "newly_isolated", "population"].sum()),
            "newly_isolated_pop_dedup": float(g.loc[g.cat == "newly_isolated", "pop_part2km"].sum()),
            "coverage60_shortfall": float(g.loc[road & ~(g.t_flood <= 60), "population"].sum() / g.loc[road, "population"].sum()),
            "top10_share": float(phs[:k].sum() / phs.sum()) if len(phs) and phs.sum() > 0 else np.nan,
            "gini_villages": gini(ph), "gini_people": gini(dl["delta"], dl["population"])}


rows, crow = [], []
rng = np.random.default_rng(SEED)
for mask in MASKS:
    f = load(mask)
    for r in (500, 1000, 2000):
        x = categorise(f, r)
        for (ev, D, T, s), g in x.groupby(["event", "D", "T", "scenario"]):
            c = {"mask": mask, "r": r, "event": ev, "D": D, "T": T, "scenario": s}
            for cat in ("no_road", "isolated_baseline", "newly_isolated", "delayed", "unaffected"):
                m = g.cat == cat
                c[f"{cat}_villages"] = int(m.sum()); c[f"{cat}_people_dedup"] = float(g.loc[m, "pop_part2km"].sum())
                c[f"{cat}_share_rhai"] = float(g.loc[m, "population"].sum() / g.population.sum())
            crow.append(c)
            rows.append({"mask": mask, "r": r, "event": ev, "D": D, "T": T, "scenario": s, **stats(g)})
cats = pd.DataFrame(crow); h = pd.DataFrame(rows)
key = ["mask", "r", "event", "D", "T"]
w = h.pivot_table(index=key, columns="scenario", values=["wmedian_flood_min", "added_ph_rhai", "newly_isolated_pop_rhai",
                                                         "coverage60_shortfall"])
h2 = pd.DataFrame({"ratio_wmedian": w[("wmedian_flood_min", "A")] / w[("wmedian_flood_min", "B")],
                   "ratio_added_ph": w[("added_ph_rhai", "A")] / w[("added_ph_rhai", "B")],
                   "ratio_newly_isolated": w[("newly_isolated_pop_rhai", "A")] / w[("newly_isolated_pop_rhai", "B")],
                   "ratio_cov60_shortfall": w[("coverage60_shortfall", "A")] / w[("coverage60_shortfall", "B")]}).reset_index()

# bootstrap for base configs (r = 1 km), village resampling stratified by district
dist_of = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "district"]).set_index(VID)["district"]
boot = []
for mask in MASKS:
    x = categorise(load(mask), 1000)
    for ev in ("2022", "2025"):
        b = x[(x.event == ev) & (x.D == 3) & (x["T"] == 0.6)]
        A = b[b.scenario == "A"].set_index(VID); B = b[b.scenario == "B"].set_index(VID)
        ids = A.index.to_numpy(); grp = dist_of.loc[ids].to_numpy()
        strata = [ids[grp == d] for d in np.unique(grp)]
        res = []
        for _ in range(2000):
            s = np.concatenate([rng.choice(st, len(st), replace=True) for st in strata])
            sa, sb = stats(A.loc[s].reset_index()), stats(B.loc[s].reset_index())
            res.append([sa["wmedian_flood_min"] / sb["wmedian_flood_min"],
                        sa["added_ph_rhai"] / sb["added_ph_rhai"] if sb["added_ph_rhai"] else np.nan,
                        sa["newly_isolated_pop_rhai"] / sb["newly_isolated_pop_rhai"] if sb["newly_isolated_pop_rhai"] else np.nan,
                        sa["coverage60_shortfall"] / sb["coverage60_shortfall"] if sb["coverage60_shortfall"] else np.nan])
        q = np.nanpercentile(np.array(res, float), [2.5, 97.5], axis=0)
        for i, nm in enumerate(["ratio_wmedian", "ratio_added_ph", "ratio_newly_isolated", "ratio_cov60_shortfall"]):
            boot.append({"mask": mask, "event": ev, "metric": nm, "lo95": q[0, i], "hi95": q[1, i]})
        print(f"bootstrap {mask} {ev} done", flush=True)
bt = pd.DataFrame(boot)
out = h.merge(h2, on=key, how="left")
cats.to_csv(TABLES / "a2_masks_categories.csv", index=False)
out.to_csv(TABLES / "a2_masks_h1h2.csv", index=False)
bt.to_csv(TABLES / "a2_masks_h2_bootstrap.csv", index=False)
pd.set_option("display.width", 250)
base = (out.r == 1000) & (out.D == 3) & (out["T"] == 0.6)
print("\nH1/H2 base (r = 1 km, D3, T0.6):\n" + out[base].round(3).to_string(index=False))
cb = (cats.r == 1000) & (cats.D == 3) & (cats["T"] == 0.6)
print("\ncategories base:\n" + cats[cb][["mask", "event", "scenario"] + [c for c in cats if c.endswith("_villages") or c.endswith("_people_dedup")]].round(0).to_string(index=False))
print("\nbootstrap 95% intervals:\n" + bt.round(3).to_string(index=False))
