"""A6 step 1: road-segment table with pre-flood features and 2022 / 2025 closure-exposure labels.

Unit: undirected road segment (two directed edges of a two-way road count once) on the shared graph of
each of the 25 village districts. Bridges are excluded (never closed under the base rule).
Labels (exposure-based, NOT observed closure): y2022 / y2025 = closed under the base rule (v1 mask,
D = 3, T = 0.6) in either direction; y2022_v2 / y2025_v2 the same under the v2 mask (reference only).
Pre-flood features at the segment midpoint (EPSG:32642):
  elevation_m, slope_deg (SRTM GL1, 90 m), twi = ln(a / tan b), a = MERIT upa (m^2) / 90 m, tan b >= 0.001
  dist_river_km (SWAI rivers_utm; HydroRIVERS-derived), dist_canal_km (SWAI canals_utm)
  highway (road class, categorical code), length_m
  dist_facility_km (nearest layer-B facility, straight line)
  pop_1km (WorldPop sum in the 23 x 23 pixel (~2 x 2 km) window centred on the midpoint)
Writes data/a6_segments.parquet.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import shapely
from scipy.ndimage import uniform_filter
from scipy.spatial import cKDTree

from _common import DATA, SWAI, PAPER, VID, log_env
import _routing as R

log_env(__file__)
nt = pd.read_parquet(DATA / "a2_normal_times.parquet")
parts = []
for dname, g in nt.groupby("district"):
    host = g.graph.iloc[0]
    e = gpd.read_parquet(PAPER / f"cache/graphs/{R.safe_name(dname)}__{host}__edges.parquet")
    br = e["bridge"].astype(str) if "bridge" in e else pd.Series("nan", index=e.index)
    e["is_bridge"] = br.str.contains("yes", case=False, na=False) | br.str.lower().isin(["true", "viaduct"])
    e["a"], e["b"] = np.minimum(e.u, e.v), np.maximum(e.u, e.v)
    lab = {}
    for ev in ("2022", "2025"):
        for m in ("v1", "v2"):
            c = R.closed_edges(dname, host, DATA, ev, 3, 0.6, mask=m)
            lab[f"y{ev}" + ("" if m == "v1" else "_v2")] = {tuple(sorted((u, v))) for u, v, k in c}
    e = e.sort_values("length").drop_duplicates(["a", "b"])           # one row per undirected segment
    e = e[~e.is_bridge & (e.a != e.b)].copy()
    for col, s in lab.items():
        e[col] = [((a, b) in s) for a, b in zip(e.a, e.b)]
    e["district"] = dname
    e["highway"] = e["highway"].astype(str).str.strip("[]").str.split(",").str[0].str.strip(" '")
    parts.append(e[["district", "a", "b", "highway", "length"] + list(lab) + ["geometry"]])
S = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs).to_crs(32642)
S = S.rename(columns={"length": "length_m"})
mid = S.geometry.interpolate(0.5, normalized=True)
mx, my = mid.x.to_numpy(), mid.y.to_numpy()
print(f"segments: {len(S):,}; positives 2022 {S.y2022.sum():,}, 2025 {S.y2025.sum():,}")

# terrain
with rasterio.open(DATA / "raw/terrain90/terrain90.tif") as r:
    v = np.array(list(r.sample(zip(mx, my)))).astype(float)
    nod = r.nodata
S["elevation_m"], S["slope_deg"], upa = v[:, 0], v[:, 1], v[:, 2]
if nod is not None:
    S.loc[S.elevation_m == nod, "elevation_m"] = np.nan
tanb = np.maximum(np.tan(np.radians(S["slope_deg"].to_numpy())), 0.001)
S["twi"] = np.log(np.maximum(upa, 1e-6) * 1e6 / 90.0 / tanb)

# water distances
def dist_to(lines, x, y):
    tree = shapely.STRtree(lines.to_numpy())
    pts = shapely.points(x, y)
    idx = tree.nearest(pts)
    return shapely.distance(pts, lines.to_numpy()[idx]) / 1000.0
# rivers_perennial.gpkg is a 770-feature subset of rivers_utm saved without a CRS: rivers_utm alone suffices
riv = gpd.read_file(SWAI / "data/rivers_utm.gpkg").to_crs(32642).geometry
can = gpd.read_file(SWAI / "data/canals_utm.gpkg").to_crs(32642).geometry
S["dist_river_km"], S["dist_canal_km"] = dist_to(riv, mx, my), dist_to(can, mx, my)

# facilities (layer B, pre-flood)
fb = R.load_facilities("B").to_crs(32642)
S["dist_facility_km"] = cKDTree(np.c_[fb.geometry.x, fb.geometry.y]).query(np.c_[mx, my])[0] / 1000.0

# population within ~1 km (focal mean x window area)
with rasterio.open(SWAI / "population_utm.tif") as r:
    a = r.read(1).astype(np.float32); a[(a == r.nodata) | (a < 0)] = 0
    foc = uniform_filter(a, size=23, mode="constant") * 23 * 23
    rr, cc = rasterio.transform.rowcol(r.transform, mx, my)
    rr, cc = np.clip(rr, 0, a.shape[0] - 1), np.clip(cc, 0, a.shape[1] - 1)
    S["pop_1km"] = foc[rr, cc]
S["mid_x"], S["mid_y"] = mx, my
S.drop(columns="geometry").to_parquet(DATA / "a6_segments.parquet", index=False)
print(S[["elevation_m", "slope_deg", "twi", "dist_river_km", "dist_canal_km", "dist_facility_km", "pop_1km", "length_m"]]
      .describe().T[["mean", "min", "50%", "max"]].round(2).to_string())
print(f"missing terrain: {S.elevation_m.isna().sum()}")
