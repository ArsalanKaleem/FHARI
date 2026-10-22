# village_master.parquet — data dictionary

Built by `01_build_village_master.py` on 2026-10-19T22:52:45. Rows: 5159.

| column | dtype | non-null | description |
|---|---|---|---|
| `village_id` | int64 | 5159 | RHAI/SWAI village id (shared; 2..5160, id 1 = empty placeholder, dropped) |
| `name` | str | 5091 | OSM place name (often Urdu script) |
| `district` | str | 5159 | GADM L3 district (RHAI = SWAI) |
| `lon` | float64 | 5159 | WGS84 longitude |
| `lat` | float64 | 5159 | WGS84 latitude |
| `osm_id` | str | 5159 | OSM node id |
| `fclass` | str | 5159 | OSM place class |
| `geometry` | geometry | 5159 | Point, EPSG:32642 (UTM 42N) |
| `population` | float64 | 5159 | WorldPop sum within 2 km of village point (RHAI/SWAI village_population.csv) |
| `min_any_A` | float64 | 5157 | RHAI any travel time, minutes, Scenario A; NaN = no path |
| `min_primary_A` | float64 | 4758 | RHAI primary travel time, minutes, Scenario A; NaN = no path |
| `min_secondary_A` | float64 | 2235 | RHAI secondary travel time, minutes, Scenario A; NaN = no path |
| `min_tertiary_A` | float64 | 958 | RHAI tertiary travel time, minutes, Scenario A; NaN = no path |
| `score_log_A` | float64 | 5159 | RHAI score_log, Scenario A |
| `score_clinical_A` | float64 | 5159 | RHAI score_clinical, Scenario A |
| `access_band_A` | str | 5159 | RHAI access_band, Scenario A |
| `min_any_B` | float64 | 5159 | RHAI any travel time, minutes, Scenario B; NaN = no path |
| `min_primary_B` | float64 | 5158 | RHAI primary travel time, minutes, Scenario B; NaN = no path |
| `min_secondary_B` | float64 | 2981 | RHAI secondary travel time, minutes, Scenario B; NaN = no path |
| `min_tertiary_B` | float64 | 958 | RHAI tertiary travel time, minutes, Scenario B; NaN = no path |
| `score_log_B` | float64 | 5159 | RHAI score_log, Scenario B |
| `score_clinical_B` | float64 | 5159 | RHAI score_clinical, Scenario B |
| `access_band_B` | str | 5159 | RHAI access_band, Scenario B |
| `n_facilities_in_range_B` | int64 | 5159 | Scenario B facilities within district + 15 km halo |
| `swai_score` | float64 | 5159 | SWAI water_access_score |
| `swai_band` | str | 5159 | SWAI band |
| `river_distance_km` | float64 | 5159 | SWAI distance to nearest river/canal water line (km) |
| `elevation_m` | float64 | 5159 | SWAI village elevation (m) |
| `rainfall_mm` | float64 | 5159 | SWAI annual rainfall |
| `dry_rain_mm` | float64 | 5159 | SWAI dry-season rainfall |
| `NDWI` | float64 | 5159 | SWAI NDWI |
| `NDVI` | float64 | 5159 | SWAI NDVI |
| `isolated_A` | bool | 5159 | True if min_any_A is NaN (no path to any facility) |
| `isolated_primary_A` | bool | 5159 | True if min_primary_A NaN |
| `isolated_B` | bool | 5159 | True if min_any_B is NaN |
| `isolated_primary_B` | bool | 5159 | True if min_primary_B NaN |
| `delta_AB_min_any` | float64 | 5157 | min_any_A - min_any_B (minutes; >0 = open data overstates) |
| `slower_under_B` | bool | 5159 | True if B travel time exceeds A by >0.01 min (RHAI tolerance; RHAI reports 17) |
