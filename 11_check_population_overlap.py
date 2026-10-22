"""Pre-A3 check 3: population double counting from overlapping 2 km village buffers.

Base (RHAI/SWAI): pop_sum = sum of WorldPop pixels (SWAI/population_utm.tif, ~88 m, EPSG:32642)
whose centre lies within 2 km of the village point (rasterstats default all_touched=False on the
2 km buffer polygons). Rebuilt here per pixel so overlap can be measured:
  multiplicity m(p) = number of village buffers containing pixel p
Alternatives (sensitivity):
  part2km   each pixel within 2 km of >= 1 village assigned to its NEAREST village only
            (same coverage as base, no double counting)
  voronoi   every pixel in the raster assigned to its nearest village, no distance limit
Writes data/village_population_alt.parquet and results/tables/check3_population.csv.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from scipy.spatial import cKDTree

from _common import SWAI, DATA, TABLES, VID, log_env

log_env(__file__)
R_M = 2000.0
vm = gpd.read_parquet(DATA / "village_master.parquet", columns=[VID, "district", "population", "geometry"])
assert vm.crs.to_epsg() == 32642
xy = np.c_[vm.geometry.x, vm.geometry.y]
tree = cKDTree(xy)

with rasterio.open(SWAI / "population_utm.tif") as r:
    a = r.read(1); T = r.transform; nod = r.nodata
rows, cols = np.nonzero((a != nod) & (a > 0))
pop = a[rows, cols].astype(np.float64)
px = T.c + (cols + 0.5) * T.a
py = T.f + (rows + 0.5) * T.e
del a
print(f"valid populated pixels: {len(pop):,}; raster total population {pop.sum()/1e6:.2f} M")

dist, near = tree.query(np.c_[px, py], k=1)
mult = np.zeros(len(pop), np.int32)
base = np.zeros(len(vm))
CH = 500_000
for i in range(0, len(pop), CH):
    sl = slice(i, i + CH)
    hits = tree.query_ball_point(np.c_[px[sl], py[sl]], R_M)
    mult[sl] = [len(h) for h in hits]
    for p, h in zip(pop[sl], hits):
        for j in h:
            base[j] += p

within = dist <= R_M
part2km = np.bincount(near[within], weights=pop[within], minlength=len(vm))
voronoi = np.bincount(near, weights=pop, minlength=len(vm))
vm["pop_base_rebuilt"], vm["pop_part2km"], vm["pop_voronoi"] = base, part2km, voronoi

diff = vm["pop_base_rebuilt"] - vm["population"]
covered = pop[mult > 0].sum()
rows_out = [
    ("raster_total_pop", pop.sum()),
    ("pop_within_2km_of_any_village (deduplicated)", covered),
    ("sum_of_village_buffers_RHAI (population col)", vm["population"].sum()),
    ("sum_of_village_buffers_rebuilt", base.sum()),
    ("rebuild_vs_RHAI_max_abs_diff_per_village", diff.abs().max()),
    ("rebuild_vs_RHAI_median_rel_diff", (diff.abs() / vm["population"].replace(0, np.nan)).median()),
    ("double_count_factor = buffer_sum / dedup_covered", base.sum() / covered),
    ("share_of_covered_pop_in_pixels_with_multiplicity>1", pop[mult > 1].sum() / covered),
    ("villages_whose_buffer_overlaps_another", int((tree.query(xy, k=2)[0][:, 1] < 2 * R_M).sum())),
    ("sum_part2km", part2km.sum()), ("sum_voronoi", voronoi.sum()),
    ("spearman_base_vs_part2km", vm["population"].corr(vm["pop_part2km"], method="spearman")),
    ("spearman_base_vs_voronoi", vm["population"].corr(vm["pop_voronoi"], method="spearman")),
]
out = pd.DataFrame(rows_out, columns=["metric", "value"])
TABLES.mkdir(parents=True, exist_ok=True)
out.to_csv(TABLES / "check3_population.csv", index=False)
vm[[VID, "district", "population", "pop_base_rebuilt", "pop_part2km", "pop_voronoi"]].to_parquet(
    DATA / "village_population_alt.parquet", index=False)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
print(out.to_string(index=False))
by = vm.groupby("district")[["population", "pop_part2km"]].sum()
by["double_count_factor"] = by["population"] / by["pop_part2km"]
print("\nby district:\n" + by.sort_values("double_count_factor", ascending=False).to_string())

# ---- sensitivity of A2 headlines to the population definition --------------------------
from _common import wquantile
fl = pd.concat([pd.read_parquet(p) for p in sorted((DATA / "a2_flood").glob("*.parquet"))], ignore_index=True)
fl = fl.merge(vm[[VID, "population", "pop_part2km", "pop_voronoi"]], on=VID)
sens = []
for (ev, D, T, s), g in fl[(fl.event == "normal") | ((fl.D == 3) & (fl["T"] == 0.6))].groupby(
        ["event", "D", "T", "scenario"], dropna=False):
    for w in ("population", "pop_part2km", "pop_voronoi"):
        tt = g["min_any"].fillna(np.inf)
        sens.append({"event": ev, "D": D, "T": T, "scenario": s, "weight": w,
                     "wmedian": wquantile(tt, g[w], 0.5), "wp90": wquantile(tt, g[w], 0.9),
                     "isolated_people": float(g.loc[g["min_any"].isna(), w].sum()),
                     "share_isolated": float(g.loc[g["min_any"].isna(), w].sum() / g[w].sum())})
sens = pd.DataFrame(sens)
sens.to_csv(TABLES / "check3_population_sensitivity_a2.csv", index=False)
print("\nA2 headline under alternative population weights:\n" + sens.to_string(index=False))
