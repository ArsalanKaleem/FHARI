"""Pre-A3 check 5: independent validation of the 2022 S1 flood mask against Dynamic World.

Reference: Dynamic World V1 (GOOGLE/DYNAMICWORLD/V1; Sentinel-2 optical, 10 m, near-real-time
land cover). Independent of our Sentinel-1 radar method. For each sample point, over the same
window (2022-08-01..2022-11-01): number of cloud-free DW observations and the share labelled
`water` or `flooded_vegetation`. Reference "flooded" = share >= 0.5 among >= 3 DW observations
(points with < 3 clear observations are excluded and counted).

Sample: stratified random points over Sindh land, from the S1 flood_days band:
  stratum fd0 (0 days), fd1_2 (1-2), fd3p (>= 3, our "treated" rule); N_PER per stratum, plus
  the same design restricted to within 30 m of the routing graph edges is NOT attempted here
  (would need an edge upload). Points with obs_days == 0 (masked) are excluded.
Metrics: precision/recall/F1/kappa of S1 fd>=3 vs DW-flooded, by stratum and weighted back to
the stratum areas. Caveats: DW is optical (cloud-limited during monsoon), and its water class
also includes permanent water; JRC GSW >= 90 % is masked in both arms.
Uses EE compute (sampleRegions over ~N points); run with --submit only.
"""
import argparse
import json

import numpy as np
import pandas as pd
import rasterio

from _common import DATA, TABLES, SEED, log_env, set_seeds

ap = argparse.ArgumentParser()
ap.add_argument("--submit", action="store_true")
ap.add_argument("--n-per", type=int, default=700)
args = ap.parse_args()
set_seeds()
log_env(__file__)
START, END = "2022-08-01", "2022-11-01"
RASTER = DATA / "raw/s1_flood/s1_flood_2022_30m.tif"
OUTCSV = DATA / "check5_dw_samples.csv"

# --- stratified sample from the local raster (strided read to stay memory-safe) ---------
rng = np.random.default_rng(SEED)
with rasterio.open(RASTER) as r:
    step = 5
    fd = r.read(2, out_shape=(r.height // step, r.width // step), resampling=rasterio.enums.Resampling.nearest)
    ob = r.read(3, out_shape=(r.height // step, r.width // step), resampling=rasterio.enums.Resampling.nearest)
    tr = r.transform * r.transform.scale(r.width / fd.shape[1], r.height / fd.shape[0])
valid = ob > 0
strata = {"fd0": valid & (fd == 0), "fd1_2": valid & (fd >= 1) & (fd <= 2), "fd3p": valid & (fd >= 3)}
area = {k: int(m.sum()) for k, m in strata.items()}
pts = []
for k, m in strata.items():
    rr, cc = np.nonzero(m)
    sel = rng.choice(len(rr), size=min(args.n_per, len(rr)), replace=False)
    x, y = rasterio.transform.xy(tr, rr[sel], cc[sel])
    pts += [{"stratum": k, "x": xi, "y": yi, "fd": int(fd[a, b])} for xi, yi, a, b in zip(x, y, rr[sel], cc[sel])]
pts = pd.DataFrame(pts)
pts["pid"] = np.arange(len(pts))
print(f"strata pixel counts (1/{step} grid): {area}; sampled {len(pts)}")
if not args.submit:
    print("dry run: no EE call"); raise SystemExit

import ee
from pyproj import Transformer

ee.Initialize(project="flood-recovery-sindh")
lon, lat = Transformer.from_crs(32642, 4326, always_xy=True).transform(pts.x.to_numpy(), pts.y.to_numpy())
fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(a), float(b)]), {"pid": int(p)})
                           for a, b, p in zip(lon, lat, pts.pid)])
dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(START, END).filterBounds(fc.geometry()).select("label")
wet = dw.map(lambda i: i.eq(0).Or(i.eq(3)).rename("wet").copyProperties(i, ["system:time_start"]))
img = wet.sum().rename("dw_wet").addBands(wet.count().rename("dw_obs"))
res = img.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=10, tileScale=4).getInfo()
got = pd.DataFrame([{"pid": f["properties"]["pid"], "dw_wet": f["properties"].get("dw_wet"),
                     "dw_obs": f["properties"].get("dw_obs")} for f in res["features"]])
pts = pts.merge(got, on="pid", how="left")
pts["lon"], pts["lat"] = lon, lat
pts.to_csv(OUTCSV, index=False)

ok = pts["dw_obs"].fillna(0) >= 3
p = pts[ok].copy()
p["ref"] = (p["dw_wet"] / p["dw_obs"]) >= 0.5
p["s1"] = p["fd"] >= 3
w = p["stratum"].map({k: area[k] / max(1, (p["stratum"] == k).sum()) for k in area})


def metrics(d, wt):
    tp = wt[d.s1 & d.ref].sum(); fp = wt[d.s1 & ~d.ref].sum(); fn = wt[~d.s1 & d.ref].sum(); tn = wt[~d.s1 & ~d.ref].sum()
    n = tp + fp + fn + tn; po = (tp + tn) / n; pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / n ** 2
    prec = tp / (tp + fp) if tp + fp else np.nan; rec = tp / (tp + fn) if tp + fn else np.nan
    return {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else np.nan,
            "accuracy": po, "kappa": (po - pe) / (1 - pe) if pe < 1 else np.nan}


rows = [{"subset": "area-weighted", "n": len(p), **metrics(p, w)},
        {"subset": "unweighted", "n": len(p), **metrics(p, pd.Series(1.0, index=p.index))}]
for k, g in p.groupby("stratum"):
    rows.append({"subset": f"stratum {k}", "n": len(g), "dw_flooded_share": g["ref"].mean()})
rows.append({"subset": "excluded (<3 clear DW obs)", "n": int((~ok).sum())})
out = pd.DataFrame(rows)
out.to_csv(TABLES / "check5_dw_validation.csv", index=False)
print(out.round(3).to_string(index=False))
