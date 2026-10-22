# Decision log

## 2026-10-19 — Phase A0

- `inspect_report.txt` / `phase0_inspect.py` did not exist anywhere under `C:\Projects`.
  Wrote `00_phase0_inspect.py` (read-only) to produce `data/inspect_report.txt`.
- Village IDs: RHAI and SWAI layers align exactly on `village_id` (5,159 shared ids, identical
  X/Y to 1e-14 deg, identical districts, identical population). `village_id = 1` is an empty
  placeholder at (0,0) present only in the RHAI gpkg and SWAI `Village.csv`/raw indicator files;
  dropped. The SWAI gpkg has no `village_id` column (not used).
- `SWAI/data/village_water_distance.csv` has 51 ids duplicated (ties between two river
  segments at equal distance). Not used; `river_distance_km` taken from `swai_with_district.csv`.
- Facility counts verified from files: A = 2,725 (`facilities_tiered.gpkg`), B = 3,308
  (`facilities_merged_final.gpkg`: 2,725 open + 583 PPHI). The "3,469" in the docstring of
  `rhai_05b_route_scenarioB.py` is stale. 616 PPHI geocoded but 583 in the merged layer
  (33 removed in merge — reason to confirm from `rhai_12_merge_facilities.py`).
- RHAI headline population-weighted medians (14.3 / 7.1, 2.01x) are computed after `dropna()`,
  i.e. excluding the 2 villages isolated under A (n = 5,157). Paper A reports both that and
  an isolation-aware version (isolated = +inf, separate category).
- Environment: own venv `paper_a/.venv` (python 3.14.7) pinned to RHAI requirement versions
  plus pyarrow; RHAI/SWAI venvs lack pyarrow and are not modified.
- A0 result: 5,159 rows, unique ids, 100% join coverage for all 5 sources. All RHAI headline
  numbers reproduce (n=5,157; 49.3 M; wmedian A 14.27 / B 7.10 min; 2.01x; unweighted medians
  19.1 / 9.2; 17 villages slower under B using RHAI's 0.01-min tolerance, 26 strictly).
- Isolation at baseline: 2 villages (9,067 people) have no path to any facility under A, 0 under
  B. 401 villages have no path to a *primary*-tier facility under A, 1 under B.
- Isolation-aware (isolated = +inf) population-weighted median is unchanged (14.27 / 7.10);
  weighted p95 = 46.3 (A) vs 19.7 (B) min.
- Implication for A2: B is slower than A for 17-26 villages, which a superset facility layer
  cannot produce on an identical graph. Most likely explanation (unverified): A and B were
  routed on non-identical OSM graphs (separate Overpass downloads). The A2 zero-closure reproduction check must be run per scenario
  against its own RHAI file, using the RHAI Overpass cache where possible.

## 2026-10-19 — Phase A1 (in progress)

- EE project `flood-recovery-sindh` authenticates. On every call EE warns that the project has
  **exceeded its noncommercial compute quota and is in restricted mode**. Small inventory queries
  still succeed; whether batch exports will run (or how slowly) is untested.
- 2025 coverage: Sentinel-1 IW VV is available over Sindh (Aug–Oct 2025: 170 scenes, 52 distinct
  dates; 2022 same window: 187 scenes, 54 dates). Only platform A appears in both windows. So no
  fallback is needed for 2025 imagery; the 2025 event window is provisional (P1).
- Existing asset `flood_duration_2022` (30 m) is already all-land (cropland restriction happens only
  in the 300 m grid aggregation) but its extent stops at lon 66.99; Sindh starts at 66.65, so a
  western strip is missing. A1 re-exports over the full Sindh boundary.
- The researcher's "Refined Lee" is a simplified 3x3 Lee-type filter; "flood duration" is a scene
  detection count (both orbits; same-day overlaps count twice). A1 exports both that count
  (`detections`, for the agreement check) and distinct-date `flood_days` plus `obs_days`.
- Segment exposure (inundated fraction, flood-days per edge) will be computed locally from the
  exported GeoTIFFs on the RHAI routing graph edges, to spend no further EE compute.
- 2026-10-20: researcher approved submitting both exports. Drive exports submitted to folder
  `paper_a_exports`: 2022 task BW57FJYTXHAYIYI7ED4KS7KO, 2025 task YPLDSFFULJFBFXD27TYKUOBI
  (both READY/queued at submission). Check with `02b_a1_task_status.py`.

## 2026-10-20 — Phase A1 results

- Exports finished and downloaded: `data/raw/s1_flood/s1_flood_{2022,2025}_30m.tif` (30 m,
  EPSG:32642, 17,687 x 15,119, bands detections / flood_days / obs_days). Masked pixels (permanent
  water, outside Sindh) were written as 0 (no nodata set); identified by `obs_days == 0`.
- CORRECTION to the A1 note above: same-day double counting is negligible. detections differs from
  flood_days in only 5,982 pixels (2022) / 3,251 (2025) of ~267 M. The researcher's count is in
  effect a calendar flood-day count.
- **A1 acceptance check (PASS):** on all 555,309 cropland cells, the new 2022 mask vs the
  researcher's `flood_dur_*.csv`: Pearson r = 1.000, MAE = 0.0003 detections, treated (>=3) share
  15.85 % vs 15.84 %, kappa = 0.9994; every district kappa >= 0.998. Expected, because it is the same
  method and imagery: this verifies reproduction/extension to all land, NOT flood-map accuracy.
  Independent validation (e.g. against UNOSAT 2022 extents) is still missing; to do.
- Graphs: RHAI's Overpass cache replayed with network blocked (`04_a2_graphs_from_cache.py`), so
  graphs come only from responses RHAI cached. Whether they are the snapshot RHAI routed on is
  tested by the A2 zero-closure reproduction check (not yet run). Cache file mtimes cluster on
  Jul 31 and Aug 5-6 (year not shown by `ls`; two download batches).
- Segment exposure: 15 m point sampling along each graph edge (`05_a1_segment_exposure.py`).
  Caveat: a 30 m pixel on a road mostly reflects the adjacent land; embankment roads may read as
  exposed while passable. Report as exposure scenarios only.
- Disk: C: has ~4 GB free (99 % used). Keep outputs compact; do not copy the RHAI cache.

## 2026-10-20 — Phase A2: zero-closure reproduction (acceptance check)

- Graph versions in RHAI cache: overpass.kumi.systems for all 25 village districts; a second
  version (overpass-api.de) for 16. NOTE: core-data and RHAI cache file mtimes share a bulk-copy
  timestamp (2026-07-31 04:24:51), so mtimes say nothing about download dates.
- **Scenario B reproduces** (`06_a2_reproduce_rhai.py`): exact (|diff| <= 1e-6 min, all four tiers)
  in 23/25 districts on the kumi graph; over all 5,159 villages, `min_any_B` differs for 3 villages,
  max 0.021 min (Badin); Tando Allahyar differs only in min_secondary/min_tertiary (<= 0.9 min, 3
  villages). Stated tolerance for B: 0.05 min on min_any -> PASS.
- **Scenario A does not reproduce at village level**: exact in 6/25 districts only, on no cached
  graph for the rest, although the A facility layer is identical (0 m, same tiers) to the open-data
  part of B. Most likely RHAI's A was routed on an OSM snapshot no longer in the cache (unverified).
- **Same-graph baseline** (`07_a2_same_graph_baseline.py`, A and B both on the B-reproducing graph):
  vs RHAI A, 443 villages change (3.65 M people), 151 by >1 min (1.07 M), 37 by >5 min, max 55.8 min
  (a cluster of 14 Dadu villages, ids 76-78, 2294-2304, become 20-56 min slower — a road link present
  in A's old snapshot is absent in the cached one). Province headline is unchanged: weighted median
  A 14.27 / B 7.10 min, 2.01x (unweighted median A 19.12 -> 19.01). Isolated villages unchanged (2/0).
- **Villages slower under B drop from 17 to 0 on a shared graph**: RHAI's Section 6 anomaly is an
  artifact of the OSM snapshot difference, not of the facility layers.
- Malir routing took 78 min on this machine (memory pressure, 173k edges, <1 GB free RAM); its RHAI
  values are exact for both A and B on kumi, so they are copied in 07 (column `source`).
- PENDING DECISION (researcher): use the same-graph baseline for A in Paper A (recommended), or RHAI's
  published A values.
- **DECISION 2026-10-20 (researcher):** Paper A uses the same-graph baseline for Scenario A
  (`data/a2_normal_times.parquet`, A and B both routed on the graph that reproduces RHAI B). RHAI's
  published A values are kept in `village_master.parquet` (`*_A` columns) for reference only.
  Every village whose A values differ from RHAI's published A is listed, all four tiers, in
  `results/tables/a2_scenarioA_paperA_vs_rhai_villages.csv`. Manuscript wording: "Scenario A was
  re-routed on the same OSM snapshot as Scenario B; province-level results are unchanged
  (2.01x); village-level differences are reported in Supplementary Table X."

## 2026-10-20 — Phase A2 results (flood-conditioned 2x2)

Base scenario = 2022, D = 3 flood-days, T = 0.6 of edge length, bridges never closed. All figures
exposure-based scenarios. Tables: `results/tables/a2_2x2_by_threshold.csv`, `a2_h1_concentration.csv`,
`a2_h2_bias_under_flood.csv`. Every district's zero-closure pass equals the 07 baseline (asserted).
- Bug fixed: graphs with no OSM `bridge` column (6 districts) crashed 08; now treated as no bridges.
- Base 2022: 13,265 edges closed. Isolated: A 241 villages / 1.15 M people; B 222 / 1.07 M (normal:
  2 / 9,067 and 0). Delayed >1 min: A 4.17 M, B 1.59 M people. Added person-hours (one one-way trip
  per resident, reachable villages only): A 1.06 M, B 0.24 M.
- Isolation sits in Dadu (B: 128 villages, 0.70 M) and Larkana (71, 0.27 M). Mechanism (base, B):
  Dadu 65 villages / 0.29 M have their own snapped node fully flooded ("village flooded"), 63 / 0.41 M
  sit on dry fragments with no reachable facility ("cut off", 43 fragments); Larkana 58 / 0.22 M
  flooded-node vs 13 / 0.05 M cut off. TODO: carry this split as two isolation sub-categories.
- 2025 (provisional window) is far milder: base 4,067 edges closed, isolated B 16 villages / 45 k.
- **H1 (concentration): supported, but partly mechanical.** Base 2022 B: 258 villages (5 %) carry
  all added person-hours; top 1 % of villages = 64 % (A: 55 %). Floods are local by nature, so the
  substantive statistic is the affected share: delayed >1 min + isolated = 2.65 M of 49.3 M (B).
- **H2 (bias under flood): direction depends on the outcome.** Median overstatement is unchanged
  (~2.0x under every scenario; floods touch too few people to move the median). Tail widens: wp90
  ratio 2.16 -> 2.66 (base). Added flood delay is overstated 4.5x by open data (range 2.1-6.8x
  across 2022 thresholds; 1.4-6.6x in 2025). Isolation is barely overstated (A 1.15 M vs B 1.07 M,
  +8 %): isolation is a property of the road network, and the extra PPHI facilities rarely sit
  inside a cut-off fragment.
- Non-monotonic added hours (e.g. T 0.3 < T 0.6 for D 3) because looser thresholds move delayed
  villages into "isolated", which is excluded from the sum. Any single objective for A7 must value
  isolation explicitly.
- **Risk for H5, flagged early:** if A7's objective is dominated by isolation, and isolation is
  nearly the same under A and B, the regret of targeting with open data may be small. Must be decided
  by how isolation enters the objective (pending researcher decision), not after seeing H5 results.

## 2026-10-20 — Decisions after A2 (researcher, final)

- **A3:** minimal but learned matcher. District-constrained candidates; features = RapidFuzz
  token-sort score (RHAI baseline), multilingual embedding similarity, candidate rank, district;
  small calibrated classifier (logistic regression or gradient boosting) with an explicit "no match"
  probability. No cross-encoder fine-tuning. Split by district, never by row. Evaluate top-1/top-5
  and calibration per district vs the RHAI fuzzy baseline; report failures (e.g. Tando Allahyar).
  Reason: the matcher only needs to supply calibrated placement probabilities for A4.
- **A5 (surrogate): SKIPPED.** Exact routing takes seconds per district (Sukkur, 103,804 edges,
  19 closure sets x 2 scenarios: 42 s; Malir about 10 s once memory pressure cleared), so a
  30-50 draw Monte Carlo is feasible with exact routing.
- **A6: deferred until after A7 and reframed.** Only 16 villages (45 k people) are isolated in 2025
  under B, too few for a village-level AUC claim. Target = road-edge closure exposure (train 2022,
  test 2025); 2025 village isolation reported descriptively only. A minimum-positives threshold for
  2025 edges is to be written here BEFORE A6 runs; if unmet, report descriptively and drop H4.
  2025 was mainly a riverine (Indus channel) flood; 2022 was widespread rain-driven flooding, so
  A6 is a transfer test across flood types.
- **2025 window:** base Aug-Oct 2025 with the same >= 3 detections rule; sensitivity window
  1 Sep-15 Oct 2025. Timing context per researcher: Sindh PDMA monsoon 2025 sitreps / flood alerts
  (pdma.gos.pk) — Guddu at high flood around 15 Sep 2025, wave reaching Sukkur within days and Kotri
  in late September. Status: researcher-supplied, NOT yet verified against the sitreps.
- **Literature:** EVPI and per-district value of information adopted, defined as in prereg_A7.md.
- **Wage source:** none yet. A7 delivered in person-hours and coverage; monetisation is an optional
  appendix run only once the researcher supplies a rural wage range.

## 2026-10-20 — Pre-A3 checks (researcher's section 2)

1. **District count** (`10_check_districts_h1.py`, `check1_districts.csv`): GADM L3 Sindh has 27
   districts; 25 contain villages and all 25 are routed (Karachi Central/South have none). All 5,159
   villages appear exactly once in A0, the normal baseline and every flood configuration. "24" in an
   earlier chat message was my error; the correct number is 25.
2. **H1** (`check2_h1_categories.csv`): mutually exclusive categories isolated_baseline /
   newly_isolated / delayed (> 0.01 min) / unaffected, summing to 5,159 in every configuration.
   Among affected (delayed) villages, base 2022: top 10 % carry 45 % (B) / 57 % (A) of added
   person-hours; village Gini 0.62 (B) / 0.69 (A); population-weighted Gini of per-person added minutes
   0.56 / 0.52. Across thresholds the top-10 % share ranges 0.37-0.69. H1 is "moderately concentrated
   among affected villages", not "a few villages carry everything".
3. **Population double counting** (`11_check_population_overlap.py`, `check3_population*.csv`): MATERIAL.
   Buffer sum 49.3 M vs 15.8 M distinct people within 2 km of any village (factor 3.16; 4,893 villages'
   buffers overlap; 66 % of covered people are in multiply-counted pixels; Hyderabad and Malir about 4.7x).
   WorldPop Sindh total 55.6 M. Rebuild matches RHAI (median rel. diff 1.3 %). Ratios and shares are
   robust (base 2022 B isolated share 2.2 % buffer vs 1.7 % partition; median A/B ratio ~2.0 both);
   absolute counts are not (isolated B 1.07 M buffer vs 0.27 M partition). The Voronoi partition (no
   distance limit) puts Karachi's urban population into villages and is not a meaningful alternative.
   PENDING: researcher to confirm reporting rule (proposal: shares under RHAI definition, absolute
   "people" only from the 2 km partition).
4. **Snapping, flooded vs cut-off, canals, imagery** (`12_...`, `15_...`, `check4_*.csv`):
   snap distance median 184 m, q90 1.40 km, q95 3.20 km, max 53 km; 14 % of villages > 1 km, 7 % > 2 km
   from their node (RHAI has no off-road access leg). Isolated (base 2022 B) by radius r (village
   connected if any reachable node within r): r = 0: 222 villages; 250 m: 221; 500 m: 199; 1 km: 150;
   2 km: 61. Flooded-node vs cut-off split about even at every r. Canals/rivers: 13.9 % of closed edges
   lie within 50 m of a mapped canal or river vs 8.3 % of all edges (Dadu 27 vs 12 %, Larkana 23 vs
   10 %); genuine (flooding follows canals/breaches) and spurious (canal water read as flood) cannot be
   separated without a pre-flood baseline. Permanent water: JRC GSW >= 90 % masked (Manchar Lake
   visibly excluded in tiles), narrow canals are below its resolution. Imagery (24 isolated + 6
   controls, S2 SWIR 1 Sep-15 Oct 2022, paired with/without mask): flood confirmed 17, partial 2,
   ambiguous 2 (Kashmore 158 riverine sand; 2397 turbid), embankment doubt 3 (village on a visibly dry
   raised road: 2163, 2194, 2154); controls consistent 5/6, one likely false negative (2899).
5. **Independent flood validation** (`13_check_flood_validation_dw.py`, `check5_dw_validation.csv`):
   Dynamic World V1 (S2 optical, independent of S1), 2,100 stratified points, Aug-Oct 2022, median 14
   clear DW observations per point. S1 fd >= 3 vs DW wet-share >= 0.5: area-weighted precision 0.48,
   recall 0.57, kappa 0.39; kappa 0.38-0.40 for DW thresholds 0.1-0.5. Agreement is high where the
   2022 flood centred (S1-flooded points DW-wet: Larkana 0.86, Dadu 0.87, Jacobabad 0.88) and very low in
   Khairpur 0.06, Sukkur 0.08, Ghotki 0.11 — the Nara/Thar desert margin, where dry sand gives low VV
   backscatter (classic SAR false positive; the researcher's pipeline has no sand/dry-season mask).
   Khairpur has the most base-closed edges of any district (4,448). UNOSAT 2022 extents were not used
   (download needs researcher approval).
6. **Shared graph** (`14_check_shared_graph.py`, `check6_*.csv`): the 17 former "slower under B"
   villages listed individually (8 Hyderabad +0.03-0.04 min; largest Sukkur 4052 +7.7 min); all have
   B - A = 0.000 on the shared graph. Dadu cluster: within Dadu and 25 km of the cluster, the shared
   graph (both cached versions identical here) lacks 18 km (20 %) of secondary, 9 km (8 %) tertiary and
   7 km (8 %) trunk road present in the independent Geofabrik extract of 2026-07-12 (major classes only).
   Cluster villages now route 50-67 km along primary roads (59-79 min) vs RHAI A 21-48 min. So the shared
   graph does miss real roads near the cluster (or they were mapped after the cache snapshot); RHAI's
   own A snapshot is unavailable, so which snapshot was more complete cannot be shown directly.

## 2026-10-20 — Decisions after the six checks (researcher, final)

1. **Flood mask v2 approved.** Dry-season Sentinel-1 water count (same pipeline: simplified Lee,
   VV < -17 dB, JRC >= 90 % masked) for Mar-Jun 2022 (applied to the 2022 event) and Mar-Jun 2025
   (applied to 2025). Current mask = **v1** (kept); dry-season-corrected = **v2**. H1/H2 reported on both.
2. **Headline regret** = E[V(x*) - V(x)] / E[V(x*) - V(no protection)] (share of achievable benefit).
   Also: absolute regret in deduplicated people, and the coverage-normalised version. If achievable
   gain is tiny, report absolute values with intervals instead of the ratio.
3. **Population reporting:** shares and ratios use the RHAI 2 km buffer definition; absolute people and
   person-hours use the deduplicated 2 km partition, described as "people within 2 km of a mapped
   village". The 49.3 M claim is dropped.
4. **Embankment sensitivity** pre-registered: trunk and primary roads never closed.
5. **Candidates:** one common set = union of the top N = 200 links under A, B and the ensemble mean.
   K in {5, 10, 20, 50}. Sensitivity: N = 1000, K = 100.
6. **Isolation definition:** RHAI snapping for baseline travel time. Under flood, isolated = no
   flood-open (reachable) node within 1 km of the village. Villages > 1 km from any road node form a
   separate "no mapped road access" category. Sensitivity 0.5 / 1 / 2 km; the 3 dry-raised-road
   villages (2163, 2194, 2154) are listed.
7. **Dadu on the July 2026 OSM extract:** rerun Dadu only and report the change in isolation; rebuild
   all districts only if material. Document RHAI differences and that the extract postdates 2022.

### Pre-registered v2 success criterion (written BEFORE any v2 result is computed or viewed)
- **Dry-season persistence mask (base):** a 30 m pixel is masked in v2 if it is flagged as water on
  >= 50 % of the distinct dry-season dates on which it was observed, with >= 5 observed dates.
  Sensitivity: >= 25 %. Masked pixels are treated like JRC permanent water (excluded, never "flooded").
- **Validation sample:** the identical 2,100-point Dynamic World sample (`data/check5_dw_samples.csv`,
  seed 20221001), same DW reference rule (wet share >= 0.5 of >= 3 clear observations).
- **Success = both:**
  (a) desert fringe (Khairpur, Sukkur, Ghotki pooled): precision (share of S1-flooded points that DW
      calls wet) rises from its v1 value to >= 0.40 AND by >= 0.25 absolute;
  (b) core districts (Dadu, Larkana, Jacobabad pooled): precision and recall each no more than 0.02
      lower than v1.
  Province-wide area-weighted kappa and the cropland-count agreement are reported as reference only.
- If (a) fails, v2 is still reported but is not called a fix; desert-fringe results are flagged.
  If (b) fails, v1 remains the base for core districts and the conflict is reported.
- **prereg_A7 FROZEN 2026-10-20:** frozen copy `docs/prereg_A7_2026-10-20.md` (read-only),
  SHA-256 3bc5919c4491de623954ec78c96df6513ec1cfb8757fc362519bb3e34b3856d0. Adds one rule beyond the researcher's list: A7 base mask = v2 if v2 meets the
  pre-registered success criterion, else v1 (both reported). Tiny-gain threshold for the headline
  ratio fixed at 1,000 deduplicated people or an interval including 0.
- Dry-season exports submitted 2026-10-20: 2022 (241 scenes, 71 dates) task 75SXDF4Z7ITC3EWY6RXJ5XKB;
  2025 (238 scenes, 70 dates) task RULNUUCQU24UQIY2UKODOUNI. Folder paper_a_exports.

## 2026-10-20 — Phase A3 results (minimal learned matcher)

- Candidates (`17_a3_candidates.py`): entities = GeoNames Sindh populated places (Latin variants) and
  OSM villages (all scripts), assigned to RHAI's buffered district candidate sets; 51,364 entity x
  district pairs (1,297 non-Latin). Equal names are no longer collapsed. Kept per facility: union of
  top 15 by token_sort and top 15 by embedding cosine (median 28). All 616 positives are recoverable.
  Embedding model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (ONNX via fastembed
  0.9.0, cached in cache/models). Labels: 616 positives (477 auto-accepted, never individually verified;
  139 manual accepts); 127 manual rejects; non-chosen candidates of positives as negatives.
- Facility "district" enters as district-level covariates (candidate-pool size, non-Latin share): a
  district one-hot cannot generalise under leave-district-out CV.
- Matcher (`18_a3_matcher.py`): 5-fold GroupKFold over districts (never by row), nested isotonic
  calibration, at-most-one-match facility distribution with explicit P(no match).
  Out-of-district results (`a3_matcher_overall.csv`, `a3_matcher_by_district.csv`):
  top-1 on positives baseline 0.985 / logreg 0.979 / gbm 0.972; top-5 1.000 / 0.998 / 0.997 (positives
  were selected by the fuzzy rule, so these favour the baseline by construction). On the 266 manually
  reviewed facilities (272 reviewed pairs; not score-selected): Brier 0.326 / 0.225 / 0.218, AUC
  0.666 / 0.698 / 0.707. Pair ECE <= 0.002 for all. Satellite validation (50): gbm mean q of the
  accepted pair 0.80 for "yes" (42), 0.27 for "no" (5), 0.71 for "unclear" (3). Chosen: gbm.
- Unlocated (740 with candidates + 1 without): P(no match) median 0.70 (IQR 0.60-0.82); 87 have a top
  candidate with q >= 0.5; none of them is a non-Latin (Urdu-script) name -> cross-script embedding
  matching contributes nothing detectable (null result). Expected placements per draw ~ sum(1 - q0) ~ 247.
  Tando Allahyar: 46 unlocated, mean P(no match) 0.72 — remains largely unsolvable, as anticipated.
- Limitation: P(no match) cannot be validated directly (no labelled true no-match facilities); its
  level rests on calibration from positives' non-chosen candidates and manual rejects. A4 must include a
  sensitivity on it (e.g. halve / double the no-match odds).
- Merge rule carried into A4: a placed PPHI facility within 250 m of an existing facility is a duplicate
  (RHAI rhai_12, DEDUPE_METRES = 250; explains 616 geocoded vs 583 in layer B).

## 2026-10-20 — Decision 7: Dadu on the Geofabrik extract of 2026-07-12 (`19_a2_dadu_geofabrik.py`)

- Source: C:/Users/Abbasi/Desktop/pakistan-260712-free.shp (read only). The extract postdates the
  2022 flood by ~4 years (roads mapped or built after 2022 are included); RHAI routed on Overpass
  responses cached ~mid-2026 (A snapshot no longer available).
- Construction effect found and controlled: a first build (geometric noding, one edge per noded
  piece) gave 11,351 closed edges when fed the CACHED edges (vs 1,471) — the length-share closure rule
  depends on how roads are split into edges (short fragments are more often >= 60 % flooded). Rebuilt
  OSMnx-style (vertex-pair edges + ox.simplify_graph): cached edges then give 17,670 edges / 1,561
  closed vs 17,711 / 1,471 native; residual construction effect on isolation ~ +20 % (104 vs 86
  villages, r = 1 km, B), attributed to false junctions at crossings (no layer info).
- Like-for-like (both built the same way), base 2022 B, r = 1 km: Geofabrik 105 villages / 119.0 k
  deduplicated people isolated vs cached-rebuilt 104 / 118.2 k (+0.7 %). NOT material -> no rebuild of
  other districts (`a2_dadu_osm_snapshot_compare.csv`).
- Dadu cluster (villages 76-78, 2294-2304): Geofabrik normal A times 23-49 min match RHAI published A
  (21-47 min); the cached/shared graph gives 58-79 min. So RHAI's A snapshot contained a road link
  that is missing from the cached snapshot and present in the 2026 extract: the shared graph is wrong
  by 20-56 min for these 13 villages. Kept as a documented defect (flag column to be added to the
  dataset); flood isolation conclusions unaffected.

## 2026-10-20 — A2 v1 under decision-6 categories (`08` rerun with radius columns, `20_a1a2_compare_masks.py`)

- 08 now stores, per village and configuration, best flood time over facility-reachable nodes within
  0.5 / 1 / 2 km and per-radius no-road flags; r = 0 columns are identical to the previous run (checked
  on Dadu and Sukkur). Previous outputs kept in `data/a2_flood_pre_radius/` (not deleted).
- Note: the r = 1 km rule also changes normal travel times (best node within 1 km), so the province
  weighted-median A/B ratio is 2.42 under it (2.01 under RHAI snapping, which remains the baseline-time
  definition per decision 6).
- **No mapped road access (> 1 km from any road node): 741 villages, 1.24 M deduplicated people (all
  configurations).** A separate category, large enough to state in the abstract.
- Base 2022 v1 (D3, T0.6, r 1 km), deduplicated people: newly isolated A 125 villages / 141,755, B 118 /
  129,976; delayed A 501 / 1.19 M, B 253 / 0.61 M; added person-hours A 278 k, B 70 k.
  2025: newly isolated 11 / 13,412 (A = B); delayed A 32, B 18 villages.
- H2 (A/B ratios, 95 % village bootstrap stratified by district, 2,000 resamples), 2022 base:
  flood wmedian time 2.42 (2.27-2.56); added person-hours 4.13 (3.36-5.16); newly isolated people
  1.06 (1.01-1.12); coverage shortfall (share not within 60 min) 3.39 (2.85-4.08).
  2025: 2.41 (2.24-2.55); 4.06 (2.47-9.48); 1.00 (1.00-1.00); 19.0 (12.5-35.2).
  So the open-data bias is large for delay and for coverage, and near zero for isolation, both years.
- H1 (affected = delayed villages), 2022 base: top-10 % share of added person-hours A 0.54 / B 0.37;
  village Gini 0.67 / 0.57; people Gini 0.47 / 0.52.
- v2 comparison pending: dry-season exports (tasks 75SXDF4Z7ITC3EWY6RXJ5XKB, RULNUUCQU24UQIY2UKODOUNI)
  still queued (READY) in restricted mode.

## 2026-10-21 — v2 mask: pre-registered validation verdict (computed before any v2 routing)

- Dry-season rasters downloaded (2022 from paper_a root, 2025 from Downloads; moved to
  data/raw/s1_flood/), grid identical to v1. Persistent (>= 50 % of >= 5 dry dates) share of observed
  land: 14.6 % (2022 dry season), 8.4 % (2025); >= 25 %: 25.9 % / 16.8 %.
- Test on the identical 2,100-point DW sample (`a1_v2_validation.csv`, `a1_v2_verdict.csv`):
  fringe (Khairpur, Sukkur, Ghotki; n 320) precision v1 0.071 -> v2 0.259 (v2s25 0.375);
  core (Dadu, Larkana, Jakobabad; n 210) precision 0.867 -> 0.862 (0.882), recall 0.673 -> 0.645 (0.626).
  **Criterion (a) FAILS** (needs >= 0.40 and +0.25; got +0.19). **Criterion (b) FAILS** (recall -0.028,
  limit -0.02). v2s25 fails both too. -> **v2 is NOT a fix.**
- Consequences, as pre-registered: v1 remains the base for all districts and for A7 (prereg_A7 §2);
  v2 is reported as a sensitivity only; desert-fringe (Khairpur/Sukkur/Ghotki) results are flagged as
  affected by SAR false positives.
- Descriptive, not a reinterpretation of the criterion: in the fringe sample, S1-flooded points fall
  126 -> 27; false positives 117 -> 20 (-83 %), true positives 9 -> 7. Fringe precision rests on few
  genuinely flooded points, so it is noisy.

## 2026-10-21 — v1 vs v2 results (sensitivity; v1 remains base per the pre-registered verdict)

- v2 segment exposure + routing completed without errors (`segment_exposure_v2/`, `a2_flood_v2/`).
  v2s25 not routed (failed validation; would add ~30 min for little information).
- Base-closed edges 2022 (B) v1 -> v2: Sukkur 2,718 -> 1,992; Ghotki 398 -> 246; Khairpur 4,448 -> 4,258;
  Dadu 1,471 -> 1,469; Larkana 1,084 -> 1,078; Jakobabad 590 -> 590.
- Village-level outcomes are essentially unchanged (`a2_masks_categories.csv`, `a2_masks_h1h2.csv`,
  `a2_masks_h2_bootstrap.csv`): 2022 base newly isolated, delayed and no-road counts identical; added
  person-hours (A, dedup) 278.1 k -> 277.8 k; H2 ratios 2022 v1 / v2: wmedian 2.415 / 2.415, added ph
  4.13 / 4.13, newly isolated 1.057 / 1.057, coverage shortfall 3.385 / 3.385; 2025 delayed A 32 -> 29
  villages, added-ph ratio 4.06 -> 3.97. **H1/H2 conclusions are robust to the mask version**: the SAR
  false positives sit on edges that are not on villages' best routes or are bypassed.
- Open: Khairpur closures barely fall under v2 although DW agreed on only 6 % of Khairpur's S1-flooded
  sample points, so those false positives are not dry-season-persistent. Hypothesis (UNVERIFIED):
  flooded rice paddies / wet soil labelled as crops by DW. Flag Khairpur in the manuscript.

## 2026-10-22 — Phase A4 results (facility ensemble, v1 mask)

- `21_a4_ensemble.py`: 741 unlocated PPHI facilities sampled from the A3 distributions (seeded per draw,
  SeedSequence(20221001)), placed on layer B; placements within 250 m of a B facility dropped (RHAI rule).
  Configurations per draw: normal, 2022 base, 2025 base (v1, D3, T0.6, bridges open); min_any,
  min_primary (r = 0), min_any_r1000. Sanity check passed in every district and draw: no village is
  slower than under layer B on normal roads. One zstd Parquet per draw in data/a4/<tag>/draws/.
- Placements per draw: base 227.1 (206-252), duplicates 19.8, no-match 493.1 (50 draws);
  no-match odds x0.5: 323.2 placed (30 draws); x2: 149.0 placed (30 draws).
- Province (base, mean and 95 % range over draws): weighted median normal time 6.54 (6.34-6.67) min vs
  A 14.27, B 7.10 -> A overstates the truth proxy 2.18x, B 1.09x. 2022 flood: coverage within 60 min
  0.989 (0.988-0.989) vs A 0.959, B 0.988; people not within 60 min (dedup) 135 k (124-143 k) vs A 817 k,
  B 147 k; newly isolated people (dedup) 122 k (114-127 k) vs A 142 k, B 130 k. 2025: not covered 22.6 k
  (12.8-26.8 k) vs A 533 k, B 28.5 k.
- P(no match) sensitivity: median 6.31 (x0.5) - 6.71 (x2) min; 2022 not covered 132-140 k; newly isolated
  122-125 k -> conclusions insensitive to the unverifiable no-match level.
- Convergence (`a4_convergence.csv`): N = 40 vs 50: village mean |change| > 0.5 min for 2.8 % of villages
  (q99 0.90 min, max 4.2 min); p95 > 0.5 min for 0.2 %; Monte Carlo SE of village mean: median 0, q99
  1.6 min. Adequate for province metrics and most villages; a few % of village means stay noisy.
  (Comparison with the full-N result is not a strict convergence test; MC SE is the primary evidence.)
- Limitations: the 583 layer-B PPHI placements are treated as fixed (auto-accepts ~84 % correct on the
  satellite sample); placements are settlement centroids; the ensemble is the truth proxy only as far as
  A3 calibration holds.

## 2026-10-22 — Phase A7 base results (2022, D3, T0.6, v1, N 200, K <= 50; frozen prereg)

- Engine (`_a7.py`): array graphs + exact incremental (decrease-only) re-routing for link reopening.
  Verified (`24_a7_verify.py`): flood times == A2 (r0 and r1km, 1e-6 min) in Dadu, Larkana, Sukkur;
  incremental == full re-route for 40 random links per district and for 5 sequential reopenings.
  Links: closed edges group into short links (Dadu 1,471 edges -> 725 links; median 2 directed edges).
  K = 0 values reproduce A2/A4 (cov60 A 0.9594, B 0.9880; added ph A 278,131; isolated A 144,030 dedup).
- Run (`25_a7_run.py`, 265 s): 52 states (A, B, 50 draws of data/a4/base); candidates = union of top 200
  by single-link cov60 gain under A, B, ensemble mean = 223 links (103 with positive gain under any state).
  Literal prereg reading: one candidate set (ranked by the primary objective) is used for all objectives.
- Headline regret (share of achievable benefit; 95 % bootstrap over draws), primary cov60:
  x_A: K5 0.866 (0.862-0.868), K10 0.536, K20 0.469 (0.464-0.475), K50 0.269 (0.267-0.272);
  x_B: K5 0.000, K10 0.046, K20 0.021 (0.020-0.021), K50 0.003; x_ens: <= 0.001 at every K.
  Absolute (dedup people) at K20: x_A 29,646 (29,571-29,684) of 63,536 achievable; x_B 1,509; x_ens 25.
  Isolation objective: x_A K10 0.119, K20 0.088, K50 0.024 (K5 0); x_B <= 0.046.
  Added person-hours objective: x_A 0.88-0.91 at every K; x_B 0.07-0.18; x_ens <= 0.04.
  cov30: x_A 0.69-0.80; cov120: x_A 0-0.12. Equity eps 1/2: x_A 0.30-0.91 (tiny-gain rule n/a: shares).
  -> **H5 supported for coverage, delay and equity objectives; small for isolation and cov120.**
  Matches the A2 expectation (open-data bias large for delay/coverage, ~0 for isolation).
- EVPI (value of resolving the 741 unlocated facilities, given B): cov60 K20 24.6 dedup people (0-74);
  K50 18.3 (0-55); ph K20 169 person-hours. Small: once the register's 583 geocoded facilities are used,
  the remaining unlocated ones hardly change targeting.
- Jaccard (K20, cov60): A-B 0.33, A-ens 0.29, B-ens 0.91; mean J with x*_d: A 0.29, B 0.90, ens 0.998.
- ILP additive check (K20, cov60): greedy vs additive top-K Jaccard A 0.82, B 0.48, ens 0.48 -> flagged
  (< 0.8): single-link gains interact strongly (links reconnecting the same fragment), so the additive
  approximation is poor; greedy remains primary as pre-registered.
- **EVPPI validation FAILED:** additive per-link province EVPI 2,066.7 vs exact 24.6 (84x). Per prereg the
  additive per-district EVPPI ranking is NOT reported. Bound instead: EVPPI_k <= EVPI ~ 25 dedup people
  (K20) for every district. Deviation (logged): exact per-district validation was not attempted; with
  EVPI ~ 25 people the ranking would not be informative anyway.
- Equity frontier (K20, draws mean): eps 0/1/2 allocations x_ens cov60 0.9949 / 0.9941 / 0.9937, Atkinson
  A1 of travel time 0.388 / 0.394 / 0.396; x_A 0.992 / 0.991 / 0.991, A1 0.407-0.415.
- Bug fixed before reporting: the tiny-gain flag compared equity shares with a 1,000-people threshold;
  now n/a for eq objectives.

## 2026-10-22 — A6 minimum-positives threshold (written BEFORE counting 2025 positives)

- A6 target: road-edge closure exposure; positive = edge closed under the base rule (v1 mask, D = 3,
  T = 0.6, bridges never closed) in the 2025 event, on the shared graphs of the 25 village districts.
  Two-way roads count once (undirected segment).
- **Threshold:** H4 is tested only if the 2025 test set has >= 200 positive segments AND they occur in
  >= 5 districts with >= 20 positives each. Reason: AUC-PR on fewer positives, clustered in few districts,
  has intervals too wide to separate the model from the baselines, and leave-district-out evaluation needs
  several districts with positives. If unmet: report 2025 exposure descriptively and drop the H4 claim.
- **Count (after the threshold was written):** 2025 v1 positive segments = 2,029; districts with >= 20:
  7 (Khairpur 957, Sukkur 545, Larkana 107, Shikarpur 102, Kashmore 81, Ghotki 72, Thatta 20).
  Under v2: 1,732; 6 districts >= 20 (Khairpur 875, Sukkur 419, Larkana 104, Shikarpur 97, Kashmore 76,
  Ghotki 34). -> The pre-registered threshold is MET.
- **Validity flag (not a change to the threshold):** 74 % of 2025 v1 positives (1,502) are in Khairpur
  and Sukkur, the desert-fringe districts where DW agreement with S1 was 6-8 % in 2022 and where v2 removes
  few closures (Khairpur 957 -> 875). An A6 test on these labels would substantially predict SAR false
  positives. Proposal for the researcher (decision needed before A6 runs): run A6 as pre-registered AND
  report a sensitivity excluding Khairpur/Sukkur/Ghotki (remaining 2025 positives: v1 455).

## 2026-10-22 — A7 sensitivity results (`25_a7_run.py` x 14 configs, `27_a7_sensitivity.py`)

- Runs: 2025 base; embankment; bridges closable; N 1000 / K 100; length budget L = 27.975 km (= length of
  the K20 base x_ens cov60 solution); 3 x 3 (D, T) grid. D1/T0.9 first failed with GEOSException "bad
  allocation" (out of memory, < 2 GB free); rerun alone succeeded. All 14 configs pass the tiny-gain rule
  (achievable cov60/iso gain >= 8,066 dedup people).
- Headline regret of x_A (cov60, K20) by config: base 0.469; D1: 0.631 / 0.524 / 0.178 (T 0.3/0.6/0.9);
  D3: 0.234 / 0.469 / 0.045; D5: 0.421 / 0.110 / 0.050; bridges 0.350; embankment 0.188; length budget
  0.280; N1000 0.461 (K100 0.155); 2025 0.220. x_B: 0.000-0.029; x_ens: 0.000-0.007.
  Isolation objective x_A: 0.000-0.138 (0 at D3/T0.9, D5/T0.9, 2025). Added person-hours x_A: 0.38-0.95;
  x_B 0.004-0.32. Oddity: x_ens ph regret 0.231 at D3/T0.3 (ph objective is non-monotone because newly
  reachable villages enter the sum; reported as is).
- **Conclusion (robust in direction, not in size):** targeting with open data forgoes a material share of
  achievable coverage benefit in every configuration except the strictest closure rules (T 0.9: 0.045-0.18),
  with size strongly dependent on the closure rule (0.05-0.63). Under the isolation objective the forgone
  share is small (<= 0.14). Using the PPHI register (B) recovers nearly all of it; the remaining 741
  unlocated facilities add little (EVPI small).
- H2 by config (`a7_h2_by_config.csv`; isolated here includes baseline-isolated villages): A/B ratio of
  coverage shortfall 2.07-19.0, isolated people 1.09-1.64, added person-hours 2.35-5.91; A/ensemble ratios
  similar or slightly larger (draw-bootstrap intervals narrow). Village-bootstrap intervals only for base
  configs (deviation, logged in 27 docstring).

## 2026-10-22 — Phase A6 results (edge-level exposure predictor; `28`-`30`)

- Terrain inputs: the flood project's `twi_approx` = -ln(tan slope) has no contributing-area term (not a
  TWI). New 90 m stack via tiled getDownloadURL (no batch queue): SRTM GL1 elevation, ee.Terrain slope,
  MERIT Hydro v1.0.1 upa; TWI = ln((upa m2 / 90 m) / max(tan slope, 0.001)). `rivers_perennial.gpkg` is a
  CRS-less 770-feature subset of rivers_utm; rivers_utm used alone.
- Segments: 547,323 undirected non-bridge segments (25 districts); positives 2022 6,609 (1.21 %),
  2025 2,026 (0.37 %). Bootstrap resamples reduced 2,000 -> 500 for A6 (AUC-PR over 547 k segments;
  not pre-registered for A6).
- Results (AUC-PR, 95 % district-cluster bootstrap; `a6_metrics.csv`):
  2022 LODO CV: gbm 0.088 (0.058-0.129; lift 7.3; ROC 0.895) vs distance-to-facility 0.026 (0.015-0.037)
  vs distance-to-river 0.010 (lift 0.83, ROC 0.42: worse than chance).
  2025 out-of-event: gbm 0.156 (0.050-0.233; lift 42; ROC 0.964) vs 0.016 (0.007-0.024) and 0.005.
  Excluding Khairpur/Sukkur/Ghotki (train + test): 2022 gbm 0.075 (0.029-0.146); 2025 gbm 0.086
  (0.016-0.203; lift 79) vs baselines <= 0.006.
  -> **H4 supported**: the model beats the distance-only baselines out-of-event, also without the fringe.
- Caveats: SHAP (`a6_shap.csv`) dominated by pop_1km (mean |SHAP| 1.92, negative: sparse population ->
  higher exposure), then slope 0.60, elevation 0.54, distance to facility 0.41; road class negative;
  distance to river 0.12. The model predicts exposure LABELS (which include SAR false positives), mostly
  "rural, unpopulated land along minor roads" — not hydrology. Calibration does not transfer (2025 ECE
  0.008 vs prevalence 0.0037): 2022 probabilities need recalibration before use in 2025.
- 2025 village isolation, descriptive only (1 km rule, base): 11 villages / 13,413 dedup people (Dadu 8,
  Khairpur 2, Kashmore 1), identical under A and B.

## 2026-10-22 — Phase A8 (paper package)

- `31_figures.py`: 6 figures (regret vs K; regret by configuration; H2 bias ratios; travel-time curves;
  A6 AUC-PR; 2022 category map). Reference dataviz palette slots 1-3 (all-pairs CVD-valid); each figure
  inspected after rendering; fixes: fig1 log-axis tick collisions and overlapping end labels, fig3 log ticks,
  fig5 legend over data.
- `32_audit_numbers.py`: every manuscript number recomputed from tables/data (~170 keys) ->
  results/paper_a_numbers.txt/.json. Hand-typed numbers removed from the skeleton (facility counts,
  satellite share, Dadu range — corrected to 21-56 min, additive EVPI now saved by 26).
- `33_zenodo_dataset.py`: zenodo/paper_a_villages.csv/.parquet (5,159 x 41), data dictionary (asserted
  complete), README with limitations, CITATION.cff and LICENSE drafts. Licence NOT chosen: ODbL 1.0
  proposed because the data derive from OSM; GADM and PPHI terms to be checked by the researcher.
  Category counts reproduce A2 (2022 B: 118 newly isolated, 253 delayed, 741 no mapped road).
- `docs/manuscript_skeleton.md` + `34_render_manuscript.py` (fails on unknown keys): 79 placeholders,
  Limitations (11 items) and Deviations-from-pre-registration pre-filled; AI-use statement flagged as
  required.
- `make_all.py`: 45 local steps (+ network/external flags). `--final` tested end to end (23 s, all OK).
  The full pipeline has NOT been re-run from scratch in one go (est. 3-4 h).
- Still open for the researcher: title choice; author list; licence; verify 2025 PDMA timing; novelty search
  in decision-theory / robust facility-location literature (required before any "first" claim); AI-use
  statement; wage range if the monetisation appendix is wanted.

## 2026-10-22 - Novelty search + reliable-facility-location read (docs/related_work_note.md)

- Correction: an earlier update of the note, skeleton and log (same day) failed on a shell quoting error and
  wrote nothing, although the session summary said it had been done. Redone with the file editor and verified.
- Closest decision analogue (read): Akhlaghi, Campbell and Demir (2023, arXiv:2302.07983), deterministic flood
  mitigation of road segments for healthcare access, facility locations taken as given.
- Reliable facility location (records): Snyder and Daskin 2005; Cui, Ouyang and Shen 2010; Berman, Krass and
  Menezes 2009 (value of information about facility STATUS); Lim et al. 2013 (cost of misestimated failure
  probabilities). None treats existing-but-unrecorded facilities or road protection.
- Novelty framed as: regret / value of information of facility-register omission in a flood road-protection
  decision, probabilistic unlocated facilities, outcome-dependent bias. Wording: "to our knowledge, based on a
  structured search". Full texts of "record" items still to read before submission; arXiv 2607.16668 unread.

## 2026-10-22 - Final manuscript for Natural Hazards (docs/paper/)

- Journal check: Natural Hazards (Springer) has NO journal-specific Word template; its Instructions for Authors
  (read 2026-10-22 via SpringerLink) ask for Word, 10-pt Times, page and line numbers, decimal headings (max 3),
  abstract 150-250 words, 4-6 keywords, author-year citations, Springer reference style with DOI links,
  "Fig. n" captions without final punctuation, Statements and Declarations after the References, and LLM use
  documented in the Methods. The manuscript follows these rules.
- `36_paper_text.py` (text; every number an audit key; figures renumbered by first citation; asserts no
  em/en dashes) -> docs/paper/paper.json; `manuscript_build/build_docx.js` (docx 9) -> NatHaz_manuscript.docx
  (schema validation PASSED); PDF exported by Microsoft Word (14 pages, 5,781 words incl. tables/references).
- Prose written to the humanizer skill rules; automated scan found no flagged vocabulary and no dashes.
- References: only works verified this session (read, record, or confirmed citation). Removed unverified details:
  Salman et al. 2010 volume/pages, Hierink et al. 2022 article number, Lundberg and Lee 2017 page range; arXiv
  paper cited by abstract URL. Unpublished RHAI / flood-recovery work mentioned in text only (journal rule).
- Figures re-rendered to journal artwork rules (600 dpi, Arial, panel labels instead of titles, line styles and
  markers in addition to colour).
- Placeholders left for the researcher: title choice (working title 2 used), author names/affiliations/ORCID,
  Funding, Competing interests, Author contributions, Zenodo DOI, and confirmation of the drafted AI-use statement.
