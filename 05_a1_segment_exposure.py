"""A1: per-road-segment flood exposure on the RHAI routing graphs (2022 and 2025).

For every edge of every district graph built by 04_a2_graphs_from_cache.py, sample points every
SPACING_M along the edge geometry (EPSG:32642) and read band `flood_days` from the 30 m S1 masks.
Points with obs_days == 0 are masked (permanent water per JRC GSW >= 90 %, typically river
crossings / bridges, or outside Sindh) and counted separately, never as "inundated".

Per edge and event:
  n_pts, frac_masked
  frac_fd_ge{1,3,5}  share of UNMASKED sampled length with flood_days >= 1 / 3 / 5
  fd_max, fd_med     max / median flood_days over unmasked points
These are EXPOSURE measures, not observed closures. A2 turns them into closure scenarios
(e.g. closed if frac_fd_ge3 >= 0.3 / 0.6 / 0.9).

Edges are processed per district with the raster window read once per district (memory-safe).
Resumable per district. Writes data/segment_exposure[_v2|_v2s25]/<district>__<mirror>.parquet.
--mask v2 / v2s25 adds the dry-season persistence mask (decision_log 2026-10-20): a pixel observed on
>= 5 dry-season dates and flagged on >= 50 % (v2) / 25 % (v2s25) of them is treated as masked.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import shapely
from rasterio.windows import from_bounds

from _common import PAPER, DATA, log_env

log_env(__file__)
SPACING_M = 15.0
GRAPHS = PAPER / "cache/graphs"
OUT = DATA / "segment_exposure"
OUT.mkdir(parents=True, exist_ok=True)
RASTERS = {yr: DATA / f"raw/s1_flood/s1_flood_{yr}_30m.tif" for yr in ("2022", "2025")}
DRY = {yr: DATA / f"raw/s1_flood/s1_dry_{yr}_30m.tif" for yr in ("2022", "2025")}
THRESH_DAYS = (1, 3, 5)
DRY_MIN_OBS = 5          # v2 rule, pre-registered 2026-10-20
DRY_THR = None           # set from --mask (None = v1, no dry-season mask)


def sample_points(lines):
    """Return (edge_index, point geometries) at ~SPACING_M along each line, endpoints included."""
    lengths = shapely.length(lines)
    n = np.maximum(2, np.ceil(lengths / SPACING_M).astype(int) + 1)
    idx = np.repeat(np.arange(len(lines)), n)
    # fractional positions 0..1 within each edge
    starts = np.repeat(np.cumsum(n) - n, n)
    pos = (np.arange(n.sum()) - starts) / np.repeat(n - 1, n)
    pts = shapely.line_interpolate_point(lines[idx], pos, normalized=True)
    return idx, pts


def exposure_for(edges, yr):
    lines = edges.geometry.to_numpy()
    idx, pts = sample_points(lines)
    x, y = shapely.get_x(pts), shapely.get_y(pts)
    with rasterio.open(RASTERS[yr]) as r:
        pad = 60
        win = from_bounds(x.min() - pad, y.min() - pad, x.max() + pad, y.max() + pad, r.transform)
        win = win.round_offsets().round_lengths()
        fd = r.read(2, window=win, boundless=True, fill_value=0)
        obs = r.read(3, window=win, boundless=True, fill_value=0)
        wt = r.window_transform(win)
    if DRY_THR is not None:          # v2: dry-season persistent water/sand is masked like JRC water
        with rasterio.open(DRY[yr]) as rd:
            assert rd.transform == r.transform and rd.shape == r.shape, "dry raster grid differs"
            dfd = rd.read(1, window=win, boundless=True, fill_value=0).astype(np.float32)
            dob = rd.read(2, window=win, boundless=True, fill_value=0).astype(np.float32)
        persistent = (dob >= DRY_MIN_OBS) & (dfd >= DRY_THR * np.maximum(dob, 1))
        obs = np.where(persistent, 0, obs)
    col = np.floor((x - wt.c) / wt.a).astype(int)
    row = np.floor((y - wt.f) / wt.e).astype(int)
    ok = (row >= 0) & (row < fd.shape[0]) & (col >= 0) & (col < fd.shape[1])
    v = np.zeros(len(x), np.int16); m = np.ones(len(x), bool)
    v[ok] = fd[row[ok], col[ok]]; m[ok] = obs[row[ok], col[ok]] == 0
    df = pd.DataFrame({"e": idx, "fd": v, "masked": m})
    g = df.groupby("e")
    res = pd.DataFrame({"n_pts": g.size(), "frac_masked": g["masked"].mean()})
    um = df[~df["masked"]]
    gu = um.groupby("e")
    for d in THRESH_DAYS:
        res[f"frac_fd_ge{d}"] = (um["fd"] >= d).groupby(um["e"]).mean()
    res["fd_max"] = gu["fd"].max()
    res["fd_med"] = gu["fd"].median()
    res = res.reindex(range(len(lines)))
    return res.add_prefix(f"y{yr}_")


ap = argparse.ArgumentParser()
ap.add_argument("--only", help="glob prefix of district graphs to process, e.g. Tando_Allahyar")
ap.add_argument("--out", type=Path, default=None, help="output folder (default by mask version)")
ap.add_argument("--mask", choices=["v1", "v2", "v2s25"], default="v1",
                help="v1 = A1 mask; v2 = minus dry-season persistence >= 0.5; v2s25 = >= 0.25")
args = ap.parse_args()
DRY_THR = {"v1": None, "v2": 0.5, "v2s25": 0.25}[args.mask]
OUT = args.out or (DATA / ("segment_exposure" if args.mask == "v1" else f"segment_exposure_{args.mask}"))
OUT.mkdir(parents=True, exist_ok=True)
edge_files = sorted(GRAPHS.glob(f"{args.only or ''}*__edges.parquet"))
print(f"{len(edge_files)} district graphs")
for f in edge_files:
    out = OUT / f.name.replace("__edges.parquet", ".parquet")
    if out.exists():
        print(f"skip {out.name}"); continue
    e = gpd.read_parquet(f).to_crs(32642)
    parts = [e[["u", "v", "key", "highway", "length", "travel_time"]].reset_index(drop=True)]
    for yr in RASTERS:
        parts.append(exposure_for(e.reset_index(drop=True), yr))
    res = pd.concat(parts, axis=1)
    res.to_parquet(out, index=False)
    print(f"{out.stem:45s} edges={len(res):,}  "
          f"2022 ge3>=60%: {(res['y2022_frac_fd_ge3'] >= 0.6).mean():.2%}  "
          f"2025 ge3>=60%: {(res['y2025_frac_fd_ge3'] >= 0.6).mean():.2%}", flush=True)
