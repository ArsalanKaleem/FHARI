"""A1 check: does the new all-land 2022 mask reproduce the researcher's per-cell flood counts?

Reference: flood-recovery-sindh/data/raw/flood_duration/flood_dur_*.csv = EE reduceRegions mean
(scale 30) of asset `flood_duration_2022` over each 300 m cropland cell of analysis_grid.gpkg.
Ours: block mean of band `detections` over the same 10x10 pixel blocks, excluding masked pixels
(Drive export stored masked pixels as 0; they are identified by obs_days == 0).

Memory-safe: rasters are read in strips aligned to the 300 m grid (machine has <1 GB free).

Also verifies at full resolution whether detections == flood_days (no same-day double counting),
and writes 300 m block means for both events (reused by later phases).

Writes:
  data/s1_flood_300m_blocks.npz           block means/valid fractions, 2022 and 2025
  results/tables/a1_agreement_overall.csv
  results/tables/a1_agreement_by_district.csv
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.windows import Window

from _common import FLOOD, DATA, TABLES, log_env, set_seeds

set_seeds()
log_env(__file__)
RAW = DATA / "raw/s1_flood"
CELL, PIX = 300, 30
K = CELL // PIX
STRIP_BLOCKS = 100          # 100 block-rows = 1,000 pixel rows per strip


def block_means(path):
    """Return dict of block arrays + grid origin (x0 = left edge, y0 = top edge, metres)."""
    with rasterio.open(path) as r:
        assert r.res == (PIX, PIX) and r.crs.to_epsg() == 32642
        left, top = r.bounds.left, r.bounds.top
        x0 = np.ceil(left / CELL) * CELL          # first 300 m grid line inside raster
        y0 = np.floor(top / CELL) * CELL
        co, ro = int((x0 - left) / PIX), int((top - y0) / PIX)
        nbr, nbc = (r.height - ro) // K, (r.width - co) // K
        det_mean = np.full((nbr, nbc), np.nan, np.float32)
        fd_mean = np.full((nbr, nbc), np.nan, np.float32)
        valid_frac = np.zeros((nbr, nbc), np.float32)
        n_det_ne_fd = 0
        for b0 in range(0, nbr, STRIP_BLOCKS):
            b1 = min(b0 + STRIP_BLOCKS, nbr)
            win = Window(co, ro + b0 * K, nbc * K, (b1 - b0) * K)
            det, fd, obs = (r.read(i, window=win).astype(np.int32) for i in (1, 2, 3))
            valid = obs > 0
            n_det_ne_fd += int(((det != fd) & valid).sum())
            shp = (b1 - b0, K, nbc, K)
            nv = valid.reshape(shp).sum(axis=(1, 3))
            sd = np.where(valid, det, 0).reshape(shp).sum(axis=(1, 3))
            sf = np.where(valid, fd, 0).reshape(shp).sum(axis=(1, 3))
            with np.errstate(invalid="ignore", divide="ignore"):
                det_mean[b0:b1] = np.where(nv > 0, sd / nv, np.nan)
                fd_mean[b0:b1] = np.where(nv > 0, sf / nv, np.nan)
            valid_frac[b0:b1] = nv / (K * K)
    return dict(det_mean=det_mean, fd_mean=fd_mean, valid_frac=valid_frac,
                x0=x0, y0=y0, n_det_ne_fd=n_det_ne_fd)


blocks = {}
for yr in ("2022", "2025"):
    blocks[yr] = block_means(RAW / f"s1_flood_{yr}_30m.tif")
    print(f"{yr}: pixels with detections != flood_days: {blocks[yr]['n_det_ne_fd']:,}")
np.savez_compressed(DATA / "s1_flood_300m_blocks.npz",
                    **{f"{y}_{k}": v for y, d in blocks.items() for k, v in d.items()})

# ---- join to the researcher's cropland cells --------------------------------------
grid = gpd.read_file(FLOOD / "data/processed/analysis_grid.gpkg", columns=["cell_id", "district"])
b = grid.geometry.bounds
ref = pd.concat([pd.read_csv(f) for f in sorted((FLOOD / "data/raw/flood_duration").glob("flood_dur_*.csv"))])
assert ref["cell_id"].is_unique
d22 = blocks["2022"]
i = np.round((d22["y0"] - b["maxy"]) / CELL).astype(int).to_numpy()
j = np.round((b["minx"] - d22["x0"]) / CELL).astype(int).to_numpy()
inside = (i >= 0) & (i < d22["det_mean"].shape[0]) & (j >= 0) & (j < d22["det_mean"].shape[1])
df = pd.DataFrame({"cell_id": grid["cell_id"], "district": grid["district"]})
df["ours"] = np.nan
df.loc[inside, "ours"] = d22["det_mean"][i[inside], j[inside]]
df = df.merge(ref, on="cell_id", how="left")
print(f"cells: grid {len(grid):,}  in raster {inside.sum():,}  with reference {df['flood_duration'].notna().sum():,}")

m = df.dropna(subset=["ours", "flood_duration"])


def agree(g):
    a, r = g["ours"], g["flood_duration"]
    ta, tr = a >= 3, r >= 3                  # researcher's treatment rule
    po = (ta == tr).mean()
    pe = ta.mean() * tr.mean() + (1 - ta.mean()) * (1 - tr.mean())
    return pd.Series({
        "n_cells": len(g), "pearson_r": a.corr(r), "spearman_rho": a.corr(r, method="spearman"),
        "mae": (a - r).abs().mean(), "mean_diff_ours_minus_ref": (a - r).mean(),
        "share_absdiff_lt_0.1": ((a - r).abs() < 0.1).mean(),
        "treated_ref_pct": 100 * tr.mean(), "treated_ours_pct": 100 * ta.mean(),
        "treated_agreement_pct": 100 * po,
        "cohen_kappa": (po - pe) / (1 - pe) if pe < 1 else np.nan})


overall = agree(m).to_frame("value")
by_d = m.groupby("district").apply(agree, include_groups=False)
TABLES.mkdir(parents=True, exist_ok=True)
overall.to_csv(TABLES / "a1_agreement_overall.csv")
by_d.to_csv(TABLES / "a1_agreement_by_district.csv")
print("\nOVERALL (2022, cropland cells):\n" + overall.to_string())
print("\nBY DISTRICT:\n" + by_d.round(3).to_string())
print(f"\nmissing ours (outside raster or fully masked): {df['ours'].isna().sum():,};  "
      f"missing reference: {df['flood_duration'].isna().sum():,}")
