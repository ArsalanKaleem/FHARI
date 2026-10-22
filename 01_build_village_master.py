"""A0: build paper_a/data/village_master.parquet (one row per village, 5,159 rows).

Sources (all joined on village_id; alignment verified in data/inspect_report.txt):
  RHAI/data/sindh_villages.gpkg         geometry (EPSG:32642), osm_id, fclass
  RHAI/data/village_population.csv      pop_sum (WorldPop, 2 km buffer)
  RHAI/data/rhai_village_scores.csv     Scenario A travel times + scores
  RHAI/data/rhai_village_scores_B.csv   Scenario B travel times + scores
  SWAI/data/swai_with_district.csv      SWAI score/band + pre-flood covariates

village_id 1 is a placeholder row at (0,0) with no attributes in the RHAI gpkg and SWAI
Village.csv; it is absent from every results table and is dropped here.

Isolation: RHAI wrote NaN when a village node had no path to any facility. Here that is
kept as NaN in tt_* columns and flagged in isolated_* (never capped or dropped).

Writes:
  data/village_master.parquet           GeoParquet, EPSG:32642, lon/lat columns kept
  results/tables/a0_join_coverage.csv
  results/tables/a0_headline_check.csv
  docs/data_dictionary_village_master.md
"""
import numpy as np
import pandas as pd
import geopandas as gpd

from _common import (RHAI, SWAI, DATA, TABLES, DOCS, VID, log_env, set_seeds,
                     wmedian, wquantile)

set_seeds()
env = log_env(__file__)
TT_COLS = ["min_any", "min_primary", "min_secondary", "min_tertiary"]

# ---- load -------------------------------------------------------------------------
geo = gpd.read_file(RHAI / "data/sindh_villages.gpkg")[[VID, "osm_id", "fclass", "geometry"]]
pop = pd.read_csv(RHAI / "data/village_population.csv")
A = pd.read_csv(RHAI / "data/rhai_village_scores.csv", encoding="utf-8")
B = pd.read_csv(RHAI / "data/rhai_village_scores_B.csv", encoding="utf-8")
S = pd.read_csv(SWAI / "data/swai_with_district.csv", encoding="utf-8")

# Base = RHAI Scenario A table (defines the 5,159-village universe)
base = A[[VID, "name", "district", "X", "Y"]].copy()
n0 = len(base)

sources = {
    "rhai_villages_gpkg": (geo, ["osm_id", "fclass", "geometry"]),
    "rhai_population": (pop.rename(columns={"pop_sum": "population"}), ["population"]),
    "rhai_A": (A.rename(columns={c: f"{c}_A" for c in TT_COLS + ["score_log", "score_clinical", "access_band"]}),
               [f"{c}_A" for c in TT_COLS] + ["score_log_A", "score_clinical_A", "access_band_A"]),
    "rhai_B": (B.rename(columns={**{c: f"{c}_B" for c in TT_COLS + ["score_log", "score_clinical", "access_band"]},
                                 "n_facilities": "n_facilities_in_range_B"}),
               [f"{c}_B" for c in TT_COLS] + ["score_log_B", "score_clinical_B", "access_band_B",
                                              "n_facilities_in_range_B"]),
    "swai": (S.rename(columns={"water_access_score": "swai_score", "band": "swai_band",
                               "district": "district_swai"}),
             ["swai_score", "swai_band", "river_distance_km", "elevation_m", "rainfall_mm",
              "dry_rain_mm", "NDWI", "NDVI", "district_swai"]),
}

coverage = []
m = base
for key, (df, cols) in sources.items():
    src_ids = set(df[VID])
    dups = int(df[VID].duplicated().sum())
    m = m.merge(df[[VID] + cols], on=VID, how="left", validate="one_to_one", indicator=True)
    matched = int((m.pop("_merge") == "both").sum())   # id present in source (values may be NaN)
    coverage.append({"source": key, "src_rows": len(df), "src_dup_ids": dups,
                     "matched": matched, "base_rows": n0, "coverage_pct": 100 * matched / n0,
                     "src_ids_not_in_base": sorted(src_ids - set(base[VID]))[:10]})
    print(f"join {key:20s} matched {matched}/{n0} ({100*matched/n0:.2f}%)  "
          f"src_rows={len(df)} src_dup_ids={dups} src_only={sorted(src_ids - set(base[VID]))[:5]}")

# ---- derived columns ---------------------------------------------------------------
assert (m["district"] == m["district_swai"]).all(), "RHAI vs SWAI district mismatch"
m = m.drop(columns="district_swai")
for s in ("A", "B"):
    m[f"isolated_{s}"] = m[f"min_any_{s}"].isna()
    m[f"isolated_primary_{s}"] = m[f"min_primary_{s}"].isna()
m["delta_AB_min_any"] = m["min_any_A"] - m["min_any_B"]   # >0: open data overstates
m["slower_under_B"] = m["delta_AB_min_any"] < -0.01   # RHAI audit tolerance (0.01 min)
m = m.rename(columns={"X": "lon", "Y": "lat"})
gdf = gpd.GeoDataFrame(m, geometry="geometry", crs=geo.crs)

# ---- acceptance check --------------------------------------------------------------
assert len(gdf) == 5159, len(gdf)
assert gdf[VID].is_unique
assert gdf.geometry.notna().all()
xy = gdf.to_crs(4326).geometry
assert np.allclose(xy.x, gdf["lon"], atol=1e-6) and np.allclose(xy.y, gdf["lat"], atol=1e-6)

# ---- headline reproduction (RHAI method: drop NaN, then weight) ---------------------
rows = []
j = gdf.dropna(subset=["min_any_A", "min_any_B", "population"])
wa, wb = wmedian(j["min_any_A"], j["population"]), wmedian(j["min_any_B"], j["population"])
rows += [("rhai_method_n_villages", len(j), 5157),
         ("rhai_method_pop_total_M", j["population"].sum() / 1e6, 49.3),
         ("rhai_method_wmedian_A_min", wa, 14.3),
         ("rhai_method_wmedian_B_min", wb, 7.1),
         ("rhai_method_overstatement_x", wa / wb, 2.01),
         ("unweighted_median_A_min", gdf["min_any_A"].median(), 19.1),
         ("unweighted_median_B_min", gdf["min_any_B"].median(), 9.2),
         ("villages_slower_under_B_tol0.01", int(gdf["slower_under_B"].sum()), 17),
         ("villages_slower_under_B_strict", int((gdf["delta_AB_min_any"] < 0).sum()), None)]
# Isolated-aware: isolated villages enter as +inf (no cap, no drop)
for s in ("A", "B"):
    tt = gdf[f"min_any_{s}"].fillna(np.inf)
    rows += [(f"isolated_villages_{s}", int(gdf[f"isolated_{s}"].sum()), None),
             (f"isolated_pop_{s}", float(gdf.loc[gdf[f"isolated_{s}"], "population"].sum()), None),
             (f"inf_aware_wmedian_{s}_min", wquantile(tt, gdf["population"], 0.5), None),
             (f"inf_aware_wp95_{s}_min", wquantile(tt, gdf["population"], 0.95), None),
             (f"isolated_primary_villages_{s}", int(gdf[f"isolated_primary_{s}"].sum()), None)]
hc = pd.DataFrame(rows, columns=["metric", "value", "rhai_reported"])
def _matches(v, r):
    """Equal after rounding v to the precision RHAI reported r at."""
    if r is None or pd.isna(r):
        return None
    dp = len(str(r).split(".")[1]) if isinstance(r, float) and "." in str(r) else 0
    return round(float(v), dp) == r


hc["matches_rhai"] = [_matches(v, r) for v, r in zip(hc["value"], hc["rhai_reported"])]
print("\nHeadline check:\n" + hc.to_string(index=False))

sl = gdf[gdf["slower_under_B"]]
print(f"\nSlower under B (B > A): {len(sl)} villages; increase median "
      f"{(-sl['delta_AB_min_any']).median():.2f} min, max {(-sl['delta_AB_min_any']).max():.2f} min; "
      f"districts {sl['district'].value_counts().to_dict()}")

# ---- write -------------------------------------------------------------------------
DATA.mkdir(exist_ok=True); TABLES.mkdir(parents=True, exist_ok=True); DOCS.mkdir(exist_ok=True)
gdf.to_parquet(DATA / "village_master.parquet", index=False)
pd.DataFrame(coverage).to_csv(TABLES / "a0_join_coverage.csv", index=False)
hc.to_csv(TABLES / "a0_headline_check.csv", index=False)

desc = {
    VID: "RHAI/SWAI village id (shared; 2..5160, id 1 = empty placeholder, dropped)",
    "name": "OSM place name (often Urdu script)", "district": "GADM L3 district (RHAI = SWAI)",
    "lon": "WGS84 longitude", "lat": "WGS84 latitude", "osm_id": "OSM node id",
    "fclass": "OSM place class", "geometry": "Point, EPSG:32642 (UTM 42N)",
    "population": "WorldPop sum within 2 km of village point (RHAI/SWAI village_population.csv)",
    **{f"{c}_{s}": f"RHAI {c.replace('min_', '')} travel time, minutes, Scenario {s}; NaN = no path"
       for s in "AB" for c in TT_COLS},
    **{f"{c}_{s}": f"RHAI {c}, Scenario {s}" for s in "AB" for c in ("score_log", "score_clinical", "access_band")},
    "n_facilities_in_range_B": "Scenario B facilities within district + 15 km halo",
    "swai_score": "SWAI water_access_score", "swai_band": "SWAI band",
    "river_distance_km": "SWAI distance to nearest river/canal water line (km)",
    "elevation_m": "SWAI village elevation (m)", "rainfall_mm": "SWAI annual rainfall",
    "dry_rain_mm": "SWAI dry-season rainfall", "NDWI": "SWAI NDWI", "NDVI": "SWAI NDVI",
    "isolated_A": "True if min_any_A is NaN (no path to any facility)",
    "isolated_B": "True if min_any_B is NaN", "isolated_primary_A": "True if min_primary_A NaN",
    "isolated_primary_B": "True if min_primary_B NaN",
    "delta_AB_min_any": "min_any_A - min_any_B (minutes; >0 = open data overstates)",
    "slower_under_B": "True if B travel time exceeds A by >0.01 min (RHAI tolerance; RHAI reports 17)",
}
lines = ["# village_master.parquet — data dictionary", "",
         f"Built by `01_build_village_master.py` on {env['run_at']}. Rows: {len(gdf)}.", "",
         "| column | dtype | non-null | description |", "|---|---|---|---|"]
for c in gdf.columns:
    lines.append(f"| `{c}` | {gdf[c].dtype} | {int(gdf[c].notna().sum())} | {desc.get(c, '')} |")
(DOCS / "data_dictionary_village_master.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nACCEPTANCE: rows={len(gdf)} (5159 expected)  unique ids={gdf[VID].is_unique}  -> PASS")
print(f"wrote {DATA / 'village_master.parquet'}")
