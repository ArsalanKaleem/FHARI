"""A6 inputs: pre-flood terrain stack for Sindh at 90 m (EPSG:32642), via tiled direct downloads.

Bands: elevation_m (SRTM GL1 v003, mean-resampled to 90 m), slope_deg (ee.Terrain.slope on SRTM),
upa_km2 (MERIT Hydro v1.0.1 upstream drainage area). TWI is computed locally as
  TWI = ln( a / tan(beta) ),  a = upa (m^2) / cell width (90 m),  tan(beta) floored at 0.001
(the flood project's `twi_approx` = -ln(tan(slope)) has no contributing-area term, so it is not used).
Tiles are fetched with getDownloadURL (interactive endpoint; batch exports queue for hours in restricted
mode) into data/raw/terrain90/tile_<i>_<j>.tif; resumable. Mosaic: data/raw/terrain90/terrain90.tif.
"""
import urllib.request

import ee
import numpy as np
import rasterio
from rasterio.merge import merge

from _common import DATA, log_env

log_env(__file__)
OUT = DATA / "raw/terrain90"; OUT.mkdir(parents=True, exist_ok=True)
ee.Initialize(project="flood-recovery-sindh")
with rasterio.open(DATA / "raw/s1_flood/s1_flood_2022_30m.tif") as r:
    left, bottom, right, top = r.bounds
dem = ee.Image("USGS/SRTMGL1_003")
img = (dem.rename("elevation_m").toFloat()
       .addBands(ee.Terrain.slope(dem).rename("slope_deg").toFloat())
       .addBands(ee.Image("MERIT/Hydro/v1_0_1").select("upa").rename("upa_km2").toFloat()))
NT = 4                                     # NT x NT tiles
xs = np.linspace(left, right, NT + 1); ys = np.linspace(bottom, top, NT + 1)
proj = ee.Projection("EPSG:32642")
for i in range(NT):
    for j in range(NT):
        f = OUT / f"tile_{i}_{j}.tif"
        if f.exists():
            continue
        reg = ee.Geometry.Rectangle([xs[i], ys[j], xs[i + 1], ys[j + 1]], proj, False)
        url = img.getDownloadURL({"region": reg, "scale": 90, "crs": "EPSG:32642", "format": "GEO_TIFF"})
        f.write_bytes(urllib.request.urlopen(url, timeout=600).read())
        print(f"tile {i},{j}: {f.stat().st_size/1e6:.1f} MB", flush=True)
srcs = [rasterio.open(p) for p in sorted(OUT.glob("tile_*.tif"))]
mos, tr = merge(srcs)
prof = srcs[0].profile | {"height": mos.shape[1], "width": mos.shape[2], "transform": tr, "compress": "deflate"}
with rasterio.open(OUT / "terrain90.tif", "w", **prof) as dst:
    dst.write(mos); dst.descriptions = ("elevation_m", "slope_deg", "upa_km2")
print("mosaic", mos.shape)
