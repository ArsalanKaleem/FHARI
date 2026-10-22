"""A1: all-land Sentinel-1 flood masks for Sindh, 2022 and 2025 events (Earth Engine).

Method reused VERBATIM from flood-recovery-sindh/gee_scripts/03_sentinel1_flood_mapping.py
(speckle filter, VV < -17 dB, JRC GSW occurrence >= 90 masked as permanent water). The source
functions are copied, not imported, so nothing is executed inside core-data; a hash check
below fails loudly if the source file changes.

NOTE on naming: the source function is called `refined_lee` but implements a simplified 3x3
Lee-type filter (its own comment says so). Report it in the paper as "simplified Lee filter".

Bands exported per event (30 m, EPSG:32642, full Sindh boundary):
  detections       sum of per-scene water flags over both orbits  == the researcher's
                   `flood_duration_days` (scene count; same-day overlapping scenes count twice)
  flood_days       number of DISTINCT calendar dates with >=1 water flag (per-date max mosaic)
  obs_days         number of distinct dates with a valid observation (denominator)
Permanent water is masked in all bands.

Usage:
  python 02_a1_flood_masks_gee.py            # dry run: inventory only, no tasks started
  python 02_a1_flood_masks_gee.py --submit   # start export tasks (ask the researcher first)
"""
import argparse
import hashlib
import json
from pathlib import Path

import ee
import geopandas as gpd

from _common import FLOOD, RHAI, LOGS, log_env

PROJECT = "flood-recovery-sindh"
VV_THRESHOLD_DB = -17.0           # from 03_sentinel1_flood_mapping.py
PERM_WATER_OCC = 90               # from 03_sentinel1_flood_mapping.py
EVENTS = {
    # 2022 window identical to the researcher's FLOOD_START/FLOOD_END.
    "2022": ("2022-08-01", "2022-11-01"),
    # 2025: same calendar window for comparability. PROVISIONAL - event dates to be
    # confirmed by the researcher (see docs/parameters_to_source.md).
    "2025": ("2025-08-01", "2025-11-01"),
}
SRC = FLOOD / "gee_scripts/03_sentinel1_flood_mapping.py"


# ---- copied verbatim from 03_sentinel1_flood_mapping.py -----------------------------
def refined_lee(img: ee.Image) -> ee.Image:
    img_linear = ee.Image(10).pow(img.divide(10))
    weights3 = ee.List.repeat(ee.List.repeat(1, 3), 3)
    kernel3 = ee.Kernel.fixed(3, 3, weights3, 1, 1, False)
    mean3 = img_linear.reduceNeighborhood(ee.Reducer.mean(), kernel3)
    variance3 = img_linear.reduceNeighborhood(ee.Reducer.variance(), kernel3)
    sample_stats = variance3.divide(mean3.multiply(mean3))
    b = sample_stats.subtract(0.25).divide(sample_stats.add(1))
    filtered = mean3.add(b.multiply(img_linear.subtract(mean3)))
    return ee.Image(10).multiply(filtered.log10()).rename("VV_filtered")


def flag_water(img: ee.Image, threshold_db: float = VV_THRESHOLD_DB) -> ee.Image:
    filtered = refined_lee(img)
    return filtered.lt(threshold_db).rename("water").copyProperties(img, ["system:time_start"])
# -------------------------------------------------------------------------------------


def check_source_unchanged():
    h = hashlib.sha256(SRC.read_bytes()).hexdigest()
    f = LOGS / "a1_source_hash.json"
    if f.exists():
        old = json.loads(f.read_text())["sha256"]
        assert old == h, f"{SRC.name} changed since first run; re-verify copied functions"
    else:
        LOGS.mkdir(exist_ok=True)
        f.write_text(json.dumps({"file": str(SRC), "sha256": h}, indent=2))
    return h


def sindh_geometry():
    b = gpd.read_file(RHAI / "data/sindh_boundary.gpkg").to_crs(4326)
    geom = b.union_all().simplify(0.005)   # ~500 m simplification, export region only
    return ee.Geometry(geom.__geo_interface__)


def s1(region, start, end):
    return (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(region).filterDate(start, end)
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .filter(ee.Filter.eq("instrumentMode", "IW")).select("VV"))


def event_image(region, start, end):
    coll = s1(region, start, end)
    flags = coll.map(flag_water)
    permanent = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gte(PERM_WATER_OCC).unmask(0)

    detections = flags.sum().rename("detections").toInt16()

    dates = coll.aggregate_array("system:time_start").map(
        lambda t: ee.Date(t).format("YYYY-MM-dd")).distinct()

    def per_date(d):
        d0 = ee.Date.parse("YYYY-MM-dd", d)
        day = flags.filterDate(d0, d0.advance(1, "day"))
        return ee.Image(day.max().rename("water"))     # any flag that day -> 1; unobserved masked

    daily = ee.ImageCollection(dates.map(per_date))
    flood_days = daily.sum().rename("flood_days").toInt16()
    obs_days = daily.count().rename("obs_days").toInt16()
    img = detections.addBands(flood_days).addBands(obs_days).updateMask(permanent.Not())
    return img, coll, dates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--events", nargs="+", default=list(EVENTS))
    args = ap.parse_args()

    log_env(__file__)
    h = check_source_unchanged()
    ee.Initialize(project=PROJECT)
    region = sindh_geometry()

    for ev in args.events:
        start, end = EVENTS[ev]
        img, coll, dates = event_image(region, start, end)
        n = coll.size().getInfo()
        orb = coll.aggregate_histogram("orbitProperties_pass").getInfo()
        print(f"[{ev}] {start}..{end}: {n} scenes, {dates.size().getInfo()} distinct dates, orbits {orb}")
        if not args.submit:
            continue
        task = ee.batch.Export.image.toDrive(
            image=img, description=f"paper_a_s1_flood_{ev}", folder="paper_a_exports",
            fileNamePrefix=f"s1_flood_{ev}_30m", region=region, scale=30, crs="EPSG:32642",
            maxPixels=1e13, fileFormat="GeoTIFF", formatOptions={"cloudOptimized": True})
        task.start()
        print(f"  submitted Drive export {task.id}")
    print(f"source sha256 {h[:12]}  ({'submitted' if args.submit else 'dry run, nothing started'})")


if __name__ == "__main__":
    main()
