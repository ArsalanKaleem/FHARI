"""A8: Zenodo-ready village dataset (one row per village) + data dictionary + README + citation stub.

Output folder: paper_a/zenodo/ (CSV UTF-8, Parquet, data_dictionary.md, README.md, CITATION.cff, LICENSE.txt)
All values are copied from pipeline outputs (no recomputation beyond simple selection and renaming).
Flood values are EXPOSURE-BASED SCENARIOS (v1 mask, D = 3 flood-days, T = 0.6 of edge length, bridges
never closed), not observed road closures.
"""
import numpy as np
import pandas as pd

from _common import DATA, TABLES, PAPER, VID, log_env

log_env(__file__)
OUT = PAPER / "zenodo"; OUT.mkdir(exist_ok=True)
vm = pd.read_parquet(DATA / "village_master.parquet",
                     columns=[VID, "name", "district", "lon", "lat", "osm_id", "min_any_A", "min_any_B"])
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "population", "pop_part2km"])
nt = pd.read_parquet(DATA / "a2_normal_times.parquet", columns=[VID, "min_any_A", "min_any_B", "min_primary_A", "min_primary_B"])
fl = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))], ignore_index=True)
VD = pd.read_parquet(DATA / "a4_village_distributions.parquet")
snap = pd.read_csv(TABLES / "check4_snapping_villages.csv")[[VID, "snap_m"]]
spot = pd.read_csv(TABLES / "check4_spotcheck.csv")[[VID, "verdict"]]
chg = pd.read_csv(TABLES / "a2_scenarioA_paperA_vs_rhai_villages.csv")[VID]

d = vm.rename(columns={"min_any_A": "rhai_pub_tt_A_min", "min_any_B": "rhai_pub_tt_B_min"})
d = d.merge(pop.rename(columns={"population": "pop_rhai_buffer2km", "pop_part2km": "pop_dedup2km"}), on=VID)
d = d.merge(nt.rename(columns={"min_any_A": "tt_normal_A_min", "min_any_B": "tt_normal_B_min",
                               "min_primary_A": "tt_normal_primary_A_min", "min_primary_B": "tt_normal_primary_B_min"}), on=VID)
en = VD[VD.config == "normal"].set_index(VID)
d = d.merge(en[["mean_min", "p05_min", "p50_min", "p95_min"]].add_prefix("tt_normal_ens_").reset_index(), on=VID)
for ev in ("2022", "2025"):
    b = fl[(fl.event == ev) & (fl.D == 3) & (fl["T"] == 0.6)]
    for s in ("A", "B"):
        x = b[b.scenario == s].set_index(VID)
        d[f"tt_flood{ev}_{s}_min"] = d[VID].map(x["min_any_r1000"])
    nrm = fl[(fl.event == "normal") & (fl.scenario == "B")].set_index(VID)
    xb = b[b.scenario == "B"].set_index(VID)
    for r in (500, 1000, 2000):
        t, tn, nr = xb[f"min_any_r{r}"], nrm[f"min_any_r{r}"], xb[f"no_road_r{r}"]
        cat = np.select([nr, tn.isna(), t.isna(), (t - tn) > 0.01],
                        ["no_mapped_road", "isolated_baseline", "newly_isolated", "delayed"], "unaffected")
        d[f"cat_flood{ev}_B_r{r}m"] = d[VID].map(pd.Series(cat, index=xb.index))
    e = VD[VD.config == ev].set_index(VID)
    d[f"tt_flood{ev}_ens_mean_min"] = d[VID].map(e["mean_min"])
    d[f"tt_flood{ev}_ens_p95_min"] = d[VID].map(e["p95_min"].replace(np.inf, np.nan))
    d[f"p_isolated_flood{ev}_ens"] = d[VID].map(e["p_isolated_r1km"])
d["no_mapped_road_1km"] = d[VID].map(nrm["no_road_r1000"])
d = d.merge(snap.rename(columns={"snap_m": "snap_distance_m"}), on=VID, how="left")
d["flag_tt_A_differs_from_rhai_pub"] = d[VID].isin(chg)
d["flag_dadu_graph_defect"] = d[VID].isin([76, 77, 78] + list(range(2294, 2305)))
d["flag_village_on_dry_raised_road"] = d[VID].isin([2163, 2194, 2154])
d["spotcheck_verdict"] = d[VID].map(spot.set_index(VID)["verdict"])
d["flag_desert_fringe_district"] = d.district.isin(["Khairpur", "Sukkur", "Ghotki"])
for c in d.columns:
    if c.endswith("_min") or c.startswith("p_isolated"):
        d[c] = d[c].astype(float).round(3)
d[["pop_rhai_buffer2km", "pop_dedup2km", "snap_distance_m"]] = d[["pop_rhai_buffer2km", "pop_dedup2km", "snap_distance_m"]].round(1)
assert len(d) == 5159 and d[VID].is_unique
d.to_csv(OUT / "paper_a_villages.csv", index=False, encoding="utf-8")
d.to_parquet(OUT / "paper_a_villages.parquet", index=False)

desc = {
    VID: "Village identifier shared with the RHAI and SWAI datasets (2..5160)",
    "name": "OSM place name (often Urdu script)", "district": "GADM 4.1 level-3 district",
    "lon": "WGS84 longitude", "lat": "WGS84 latitude", "osm_id": "OpenStreetMap node id",
    "rhai_pub_tt_A_min": "RHAI published travel time, Scenario A (open data), minutes; empty = no path",
    "rhai_pub_tt_B_min": "RHAI published travel time, Scenario B (open data + geocoded PPHI), minutes",
    "pop_rhai_buffer2km": "WorldPop sum within 2 km (RHAI definition; buffers overlap, totals double-count ~3.2x) — use for shares",
    "pop_dedup2km": "WorldPop within 2 km assigned to the nearest village only (no double counting) — use for absolute counts",
    "tt_normal_A_min": "Paper A normal-roads travel time to any facility, layer A, same OSM graph as B (RHAI snapping), minutes",
    "tt_normal_B_min": "Same, layer B", "tt_normal_primary_A_min": "Same, nearest primary-tier facility, layer A",
    "tt_normal_primary_B_min": "Same, nearest primary-tier facility, layer B",
    "tt_normal_ens_mean_min": "Ensemble (50 draws: layer B + probabilistic placement of 741 unlocated PPHI facilities): mean normal travel time",
    "tt_normal_ens_p05_min": "Ensemble 5th percentile", "tt_normal_ens_p50_min": "Ensemble median", "tt_normal_ens_p95_min": "Ensemble 95th percentile",
    "no_mapped_road_1km": "True if no road node lies within 1 km of the village point (separate category; excluded from flood isolation)",
    "snap_distance_m": "Distance from village point to its snapped road node (m)",
    "flag_tt_A_differs_from_rhai_pub": "True if any Paper A layer-A time differs from RHAI's published A (different OSM snapshot)",
    "flag_dadu_graph_defect": "True for 14 Dadu cluster villages (13 with a path) whose normal time is 20-56 min too slow on the shared graph (missing road link)",
    "flag_village_on_dry_raised_road": "True for 3 villages seen on visibly dry raised roads in Sentinel-2 imagery (isolation may be overstated)",
    "spotcheck_verdict": "Sentinel-2 visual spot-check verdict (30 villages only)",
    "flag_desert_fringe_district": "True in Khairpur, Sukkur, Ghotki, where SAR flood detections are largely false positives (Dynamic World check)",
}
for ev in ("2022", "2025"):
    desc[f"tt_flood{ev}_A_min"] = f"{ev} flood (exposure scenario), layer A: best time over facility-reachable road nodes within 1 km, minutes; empty = isolated or no road"
    desc[f"tt_flood{ev}_B_min"] = f"Same, layer B"
    for r in (500, 1000, 2000):
        desc[f"cat_flood{ev}_B_r{r}m"] = f"{ev} category, layer B, radius {r} m: no_mapped_road / isolated_baseline / newly_isolated / delayed (>0.01 min) / unaffected"
    desc[f"tt_flood{ev}_ens_mean_min"] = f"{ev} flood, ensemble mean time at the snapped node (draws with a path), minutes"
    desc[f"tt_flood{ev}_ens_p95_min"] = f"{ev} flood, ensemble 95th percentile (empty if isolated in >5 % of draws)"
    desc[f"p_isolated_flood{ev}_ens"] = f"{ev} flood, share of ensemble draws in which the village is isolated (1 km rule)"
lines = ["# paper_a_villages — data dictionary", "", f"Rows: {len(d):,} villages. Encoding UTF-8. Missing = empty.", "",
         "| column | type | non-null | description |", "|---|---|---|---|"]
for c in d.columns:
    lines.append(f"| `{c}` | {d[c].dtype} | {int(d[c].notna().sum()):,} | {desc.get(c, '')} |")
(OUT / "data_dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
missing = [c for c in d.columns if c not in desc]
assert not missing, f"undocumented columns: {missing}"
print(f"wrote {OUT / 'paper_a_villages.csv'}: {d.shape}; dictionary complete")
