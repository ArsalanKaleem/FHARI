# FHARI

Flood-conditioned access to primary health care in Sindh, Pakistan, under incomplete facility data.

This repository holds the analysis pipeline for a study that asks what it costs to target flood-resilience
road protection with incomplete health facility data. Open geospatial data miss most rural public primary
care facilities in Sindh. We route travel from 5,159 OpenStreetMap villages to the nearest facility under
three facility layers, close roads that Sentinel-1 radar shows as flooded in 2022 and 2025, and measure how
much of the achievable benefit a road-protection plan forgoes when it is chosen with open data only.

## Headline results

All numbers are recomputed by `32_audit_numbers.py` (`results/paper_a_numbers.txt`). Flood results are
exposure scenarios, not observed road closures.

| Result | Value |
|---|---|
| Villages / districts | 5,159 / 25 |
| Facilities: open data (A) / plus geocoded PPHI register (B) / unlocated register facilities | 2,725 / 3,308 / 741 |
| Population-weighted median travel time, normal roads: A / B / facility ensemble | 14.27 / 7.10 / 6.54 min |
| Share of achievable 60-min coverage gain forgone when 20 links are chosen with open data (2022) | 0.469 (95 % interval 0.464 to 0.474) |
| Same, across pre-registered closure rules | 0.045 to 0.631 |
| Same, with the isolation objective | 0.088 |
| Same, when links are chosen with the register (B) | 0.020 |
| Value of locating all remaining unlocated facilities (EVPI, K = 20) | 24.6 people |
| Open-data bias under flood (A/B, 2022): added person-hours / newly isolated population | 4.13 / 1.06 |
| Road exposure predictor, 2025 out-of-event AUC-PR: model / distance-to-facility baseline | 0.156 / 0.016 |

## Research questions

- **H1** Are flood delay and isolation concentrated in a small share of villages?
- **H2** Does the open-data bias change under flood conditions, and does it differ by outcome?
- **H4** Does a model trained on 2022 road exposure predict 2025 exposure better than distance baselines?
- **H5** Does targeting road protection with open data forgo a measurable share of the achievable benefit?

The H5 analysis was pre-registered before any result was computed (`docs/prereg_A7_2026-10-20.md`, SHA-256
in `docs/decision_log.md`).

## Pipeline

Scripts are numbered in execution order. Phases follow the project plan (A5, a surrogate model, was not needed
because exact routing takes seconds per district).

| Phase | Scripts | What it does |
|---|---|---|
| A0 | `00`, `01` | Inspect inputs; build the village master table |
| A1 | `02`, `02b`, `03`, `05`, `16` | Sentinel-1 flood masks (Earth Engine), agreement check, road segment exposure, dry-season mask |
| A2 | `04`, `06`-`09`, `19` | Rebuild road graphs from the cached Overpass responses, reproduce the earlier routing, shared-graph baseline, flood routing, summaries |
| Checks | `10`-`15`, `20` | District coverage, H1 categories, population double counting, snapping and canals, Dynamic World validation, imagery spot-check, v1 vs v2 masks |
| A3 | `17`, `18` | District-constrained candidates and a calibrated matcher for unlocated register facilities |
| A4 | `21`, `22` | Monte Carlo facility ensemble and convergence |
| A7 | `24`-`27` | Engine verification, greedy targeting, regret / EVPI, sensitivity |
| A6 | `28`-`30` | Terrain download, road segment table, edge-level exposure predictor |
| A8 | `31`-`33`, `make_all.py` | Figures, number audit, village data set |

Shared modules: `_common.py` (paths, seed, environment logging), `_routing.py` (routing identical to the
original travel-time index), `_a7.py` (exact incremental rerouting for road protection).

## Repository layout

| Path | Contents |
|---|---|
| `*.py` | Pipeline scripts |
| `data/` | Small inputs needed to regenerate the final tables and figures (see below) |
| `results/tables/`, `results/figures/` | All result tables and figures; `results/paper_a_numbers.*` is the audit |
| `docs/decision_log.md` | Every decision, check and result with its date. Read this first |
| `docs/prereg_A7*.md` | Pre-registration of the targeting analysis |
| `docs/related_work_note.md` | Literature note with verification levels |
| `docs/parameters_to_source.md` | Parameters that are not yet sourced |
| `logs/*.env.json` | Python and package versions and the random seed for each script |

## Running it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python make_all.py --list                     # the ordered plan
.venv/Scripts/python make_all.py --final                    # regenerate tables, figures and the audit
```

`--final` works from the files in this repository. The full pipeline (`make_all.py` without flags, about 3 to
4 hours) also needs inputs that are not versioned here:

- the parent `core-data/` folder with the earlier projects' data (`RHAI/`, `SWAI/`, `flood-recovery-sindh/`),
  which `_common.py` expects next to this folder;
- the cached Overpass responses of the travel-time project (`04_a2_graphs_from_cache.py`);
- Sentinel-1 flood and dry-season rasters exported with `02` and `16` (Google Earth Engine project needed) and
  downloaded into `data/raw/s1_flood/`;
- for `19`, a Geofabrik Pakistan roads shapefile given by the environment variable `GEOFABRIK_ROADS`.

Steps that need Earth Engine run only with `--network`; step 19 only with `--external`.

## What is not in this repository

The manuscript, the Zenodo data deposit, the Python environment, the road graph cache and large intermediate
data (flood rasters, segment exposures, segment tables and ensemble draws) are excluded to keep the
repository small. They are regenerated by the pipeline.

## Limitations

Flood closures are exposure scenarios: radar shows water, not passability. The radar map has false detections on
the desert margin (Khairpur, Sukkur, Ghotki; agreement with Dynamic World kappa 0.39 overall). The village layer is
an OpenStreetMap sample, 741 villages have no mapped road within 1 km, and the walk to the road is not timed. The
facility ensemble depends on a matcher whose "no match" probabilities cannot be validated directly. Facilities are
assumed to work during floods. See `docs/decision_log.md` for the full list.

## Data sources

OpenStreetMap (© OpenStreetMap contributors, ODbL), WorldPop, GeoNames, GADM 4.1, Copernicus Sentinel-1 and
Sentinel-2 via Google Earth Engine, JRC Global Surface Water, Dynamic World, SRTM and MERIT Hydro, and the
PPHI Sindh facility register. Derived data in `data/` inherit the OpenStreetMap licence terms.

## Licence and citation

A licence for the code has not been chosen yet. Citation details will be added when the accompanying paper is
published.
