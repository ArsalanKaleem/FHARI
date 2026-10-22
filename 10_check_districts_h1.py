"""Pre-A3 checks 1 and 2.

Check 1 — district coverage: every GADM L3 Sindh district, its village count, whether it was
routed, and confirmation that all 5,159 villages appear exactly once in the A2 outputs.

Check 2 — H1 with mutually exclusive categories per (event, D, T, scenario):
  isolated_baseline  no path to any facility even on normal roads
  newly_isolated     reachable normally, no path under flood
  delayed            reachable in both, flood time exceeds normal by > EPS_MIN
  unaffected         reachable in both, added time <= EPS_MIN
"Affected" = delayed only (isolated villages have no finite added time and are reported
separately). Concentration among affected villages only:
  top10_share   share of total added person-hours borne by the top 10 % of affected villages
                (ranked by village added person-hours)
  gini_villages Gini of village added person-hours among affected villages
  gini_people   population-weighted Gini of per-person added minutes among affected villages

Writes results/tables/check1_districts.csv, check2_h1_categories.csv.
"""
import numpy as np
import pandas as pd

from _common import DATA, TABLES, VID, log_env
import _routing as R

log_env(__file__)
EPS_MIN = 0.01          # RHAI audit tolerance

# ---- check 1 ---------------------------------------------------------------------------
vm = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "district", "population"])
nt = pd.read_parquet(DATA / "a2_normal_times.parquet", columns=[VID, "district", "graph", "source"])
fl = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))], ignore_index=True)
gadm = sorted(R.districts()["district"].unique())
c1 = pd.DataFrame({"district": gadm})
c1["villages_master"] = c1["district"].map(vm["district"].value_counts()).fillna(0).astype(int)
c1["villages_routed_normal"] = c1["district"].map(nt["district"].value_counts()).fillna(0).astype(int)
c1["villages_routed_flood"] = c1["district"].map(fl.drop_duplicates(VID)["district"].value_counts()).fillna(0).astype(int)
c1["graph"] = c1["district"].map(nt.drop_duplicates("district").set_index("district")["graph"])
c1["source"] = c1["district"].map(nt.drop_duplicates("district").set_index("district")["source"])
c1.to_csv(TABLES / "check1_districts.csv", index=False)
print(c1.to_string(index=False))
dup = fl.groupby(["scenario", "event", "D", "T"], dropna=False)[VID].agg(["size", "nunique"])
print(f"\nGADM Sindh L3 districts: {len(gadm)}; with villages: {(c1.villages_master > 0).sum()}; "
      f"routed: {(c1.villages_routed_flood > 0).sum()}")
print(f"villages: master {vm[VID].nunique()}, normal {nt[VID].nunique()} (rows {len(nt)}), "
      f"flood per config size==nunique==5159: {bool((dup['size'].eq(5159) & dup['nunique'].eq(5159)).all())}")
assert set(vm[VID]) == set(nt[VID]) == set(fl[VID]) and len(nt) == 5159
assert (vm.set_index(VID)["district"] == nt.set_index(VID).loc[vm[VID], "district"].to_numpy()).all()

# ---- check 2 ---------------------------------------------------------------------------
fl = fl.merge(vm[[VID, "population"]], on=VID)
fl[["D", "T"]] = fl[["D", "T"]].fillna(0)
norm = fl[fl["event"] == "normal"][[VID, "scenario", "min_any"]].rename(columns={"min_any": "normal"})
f = fl[fl["event"] != "normal"].merge(norm, on=[VID, "scenario"])
delta = f["min_any"] - f["normal"]
f["category"] = np.select(
    [f["normal"].isna(), f["min_any"].isna(), delta > EPS_MIN],
    ["isolated_baseline", "newly_isolated", "delayed"], default="unaffected")
f["added_ph"] = np.where(f["category"] == "delayed", delta / 60 * f["population"], 0.0)
f["added_min"] = np.where(f["category"] == "delayed", delta, 0.0)


def gini(x, w=None):
    x = np.asarray(x, float); w = np.ones_like(x) if w is None else np.asarray(w, float)
    o = np.argsort(x); x, w = x[o], w[o]
    cw = np.cumsum(w); cxw = np.cumsum(x * w)
    if cxw[-1] <= 0:
        return np.nan
    L = np.concatenate([[0], cxw / cxw[-1]]); P = np.concatenate([[0], cw / cw[-1]])
    return float(1 - np.sum((P[1:] - P[:-1]) * (L[1:] + L[:-1])))


rows = []
for (ev, D, T, s), g in f.groupby(["event", "D", "T", "scenario"]):
    r = {"event": ev, "D": D, "T": T, "scenario": s}
    for c in ("isolated_baseline", "newly_isolated", "delayed", "unaffected"):
        m = g["category"] == c
        r[f"{c}_villages"] = int(m.sum()); r[f"{c}_pop"] = float(g.loc[m, "population"].sum())
    a = g[g["category"] == "delayed"]
    ph = np.sort(a["added_ph"].to_numpy())[::-1]
    k = max(1, int(np.ceil(0.10 * len(ph)))) if len(ph) else 0
    r.update({"added_ph_total": float(ph.sum()),
              "top10_share_affected": float(ph[:k].sum() / ph.sum()) if len(ph) and ph.sum() > 0 else np.nan,
              "gini_villages_affected": gini(ph) if len(ph) > 1 else np.nan,
              "gini_people_affected": gini(a["added_min"], a["population"]) if len(a) > 1 else np.nan,
              "mean_added_min_affected_popw": float(np.average(a["added_min"], weights=a["population"])) if len(a) else np.nan})
    assert sum(r[f"{c}_villages"] for c in ("isolated_baseline", "newly_isolated", "delayed", "unaffected")) == 5159
    rows.append(r)
c2 = pd.DataFrame(rows)
c2.to_csv(TABLES / "check2_h1_categories.csv", index=False)
base = c2[(c2.event == "2022") & (c2.D == 3) & (c2["T"] == 0.6)]
print("\nH1 base (2022, D3, T0.6):\n" + base.T.to_string())
print("\nH1 concentration among affected, all configs:\n" +
      c2[["event", "D", "T", "scenario", "delayed_villages", "top10_share_affected", "gini_villages_affected",
          "gini_people_affected"]].round(3).to_string(index=False))
