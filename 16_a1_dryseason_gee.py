"""A1 v2: dry-season Sentinel-1 water persistence (Mar-Jun) for the v2 flood mask.

Identical pipeline to 02_a1_flood_masks_gee.py (functions imported from it: simplified Lee filter,
VV < -17 dB, JRC GSW >= 90 % masked), applied to the pre-monsoon dry season of each event year:
  2022 event -> 2022-03-01 .. 2022-07-01
  2025 event -> 2025-03-01 .. 2025-07-01
Bands (30 m, EPSG:32642, same region and grid as the v1 exports):
  dry_flood_days  distinct dates with a water flag
  dry_obs_days    distinct dates observed
v2 rule (pre-registered in decision_log.md, 2026-10-20): pixel masked if
  dry_flood_days / dry_obs_days >= 0.5 with dry_obs_days >= 5   (sensitivity 0.25).
Usage: dry run by default; --submit starts the Drive exports (folder paper_a_exports).
"""
import argparse
import importlib.util

import ee

from _common import PAPER, LOGS, log_env

spec = importlib.util.spec_from_file_location("a1", PAPER / "02_a1_flood_masks_gee.py")
a1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(a1)

DRY = {"2022": ("2022-03-01", "2022-07-01"), "2025": ("2025-03-01", "2025-07-01")}

ap = argparse.ArgumentParser()
ap.add_argument("--submit", action="store_true")
args = ap.parse_args()
log_env(__file__)
a1.check_source_unchanged()
ee.Initialize(project=a1.PROJECT)
region = a1.sindh_geometry()
log = []
for yr, (start, end) in DRY.items():
    img, coll, dates = a1.event_image(region, start, end)
    img = img.select(["flood_days", "obs_days"], ["dry_flood_days", "dry_obs_days"])
    n = coll.size().getInfo(); nd = dates.size().getInfo()
    print(f"[dry {yr}] {start}..{end}: {n} scenes, {nd} distinct dates")
    if not args.submit:
        continue
    task = ee.batch.Export.image.toDrive(
        image=img, description=f"paper_a_s1_dry_{yr}", folder="paper_a_exports",
        fileNamePrefix=f"s1_dry_{yr}_30m", region=region, scale=30, crs="EPSG:32642",
        maxPixels=1e13, fileFormat="GeoTIFF", formatOptions={"cloudOptimized": True})
    task.start()
    log.append(f"submitted Drive export {task.id} dry {yr}")
    print(f"  submitted Drive export {task.id}")
if log:
    (LOGS / "a1_dry_submit.log").write_text("\n".join(log) + "\n")
