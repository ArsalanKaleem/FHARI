"""Pre-A3 check 4 (visual): Sentinel-2 spot-check of isolated and control villages.

Sample: data/check4_spotcheck_candidates.csv (12 flooded_node + 12 cut_off, base 2022 B) plus
6 controls = villages classed unaffected in base 2022 B in Dadu/Larkana (seeded draw).
Per village: 4 x 4 km Sentinel-2 SR (harmonized) median, 2022-09-01..2022-10-15, scenes with
CLOUDY_PIXEL_PERCENTAGE < 40, SWIR false colour (B12, B8, B4; open water ~ black / dark blue),
overlaid with our S1 flood mask (asset flood_duration_2022 >= 3, cyan, 45 % opacity) and the
village point (red). The verdict column of results/tables/check4_spotcheck.csv is filled by
hand after viewing results/figures/check4_spotcheck_sheet.png.
"""
import io
import urllib.request

import ee
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from _common import DATA, FIGS, TABLES, VID, SEED, log_env

log_env(__file__)
ee.Initialize(project="flood-recovery-sindh")
cand = pd.read_csv(DATA / "check4_spotcheck_candidates.csv")
fl = pd.read_parquet(DATA / "a2_flood/Dadu.parquet"), pd.read_parquet(DATA / "a2_flood/Larkana.parquet")
fl = pd.concat(fl)
nt = pd.read_parquet(DATA / "a2_normal_times.parquet", columns=[VID, "min_any_B"])
b = fl[(fl.event == "2022") & (fl.D == 3) & (fl["T"] == 0.6) & (fl.scenario == "B")].merge(nt, on=VID)
ctrl_ids = b[(b.min_any - b.min_any_B).abs() <= 0.01][VID].sample(6, random_state=SEED)
vm = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "name", "district", "lon", "lat", "population"])
ctrl = vm[vm[VID].isin(ctrl_ids)].assign(kind="control_unaffected")
sample = pd.concat([cand[[VID, "district", "kind", "lon", "lat", "population", "snap_m"]], ctrl], ignore_index=True)

s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate("2022-09-01", "2022-10-15")
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)))
flood = ee.Image("projects/flood-recovery-sindh/assets/flood_duration_2022").gte(3).selfMask()
OUT = FIGS / "check4_spotcheck"
OUT.mkdir(parents=True, exist_ok=True)
tiles = []
for _, r in sample.iterrows():
    pt = ee.Geometry.Point([float(r.lon), float(r.lat)])
    box = pt.buffer(2000).bounds()
    base = s2.filterBounds(box).median().visualize(bands=["B12", "B8", "B4"], min=0, max=3500)
    over = flood.visualize(palette=["00ffff"], opacity=0.45)
    dot = ee.Image().paint(ee.FeatureCollection([ee.Feature(pt.buffer(60))]), 1).visualize(palette=["ff0000"])
    img = ee.ImageCollection([base, over, dot]).mosaic()
    url = img.getThumbURL({"region": box, "dimensions": 400, "format": "png"})
    png = OUT / f"v{int(r[VID])}.png"
    if not png.exists():
        png.write_bytes(urllib.request.urlopen(url, timeout=120).read())
    raw = OUT / f"v{int(r[VID])}_s2only.png"          # same tile without the flood overlay
    if not raw.exists():
        url2 = ee.ImageCollection([base, dot]).mosaic().getThumbURL({"region": box, "dimensions": 400, "format": "png"})
        raw.write_bytes(urllib.request.urlopen(url2, timeout=120).read())
    tiles.append((r, png, raw))
    print(f"{int(r[VID])} {r.kind}", flush=True)

for part, chunk in enumerate((tiles[:15], tiles[15:]), start=1):     # pairs: S2 only | S2 + S1 mask
    fig, axes = plt.subplots(5, 6, figsize=(18, 5 * 3.3))
    for ax in axes.ravel():
        ax.axis("off")
    for k, (r, png, raw) in enumerate(chunk):
        a1, a2 = axes.ravel()[2 * k], axes.ravel()[2 * k + 1]
        a1.imshow(Image.open(raw)); a2.imshow(Image.open(png))
        a1.set_title(f"{int(r[VID])} {r.district} {r.kind}\nS2 only", fontsize=8)
        a2.set_title("+ S1 mask (cyan)", fontsize=8)
    fig.suptitle(f"Spot-check part {part}: S2 SWIR false colour 1 Sep-15 Oct 2022 (water dark), red = village",
                 fontsize=10)
    fig.tight_layout(); fig.savefig(FIGS / f"check4_spotcheck_sheet_part{part}.png", dpi=100); plt.close(fig)
sample.assign(verdict="", note="").to_csv(TABLES / "check4_spotcheck.csv", index=False)
print("sheet written")
