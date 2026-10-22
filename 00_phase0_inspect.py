"""Phase 0: read-only inspection of village-level sources in core-data.

Writes paper_a/data/inspect_report.txt. Touches nothing outside paper_a/.
Answers: do RHAI and SWAI village layers share IDs, coordinates and districts?
What columns exist? Which IDs are duplicated, missing, or non-finite?
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]          # core-data/
OUT = Path(__file__).resolve().parent / "data" / "inspect_report.txt"

SOURCES = {
    "rhai_villages_gpkg": ROOT / "RHAI/data/sindh_villages.gpkg",
    "swai_villages_gpkg": ROOT / "SWAI/data/sindh_villages.gpkg",
    "rhai_scores_A": ROOT / "RHAI/data/rhai_village_scores.csv",
    "rhai_scores_B": ROOT / "RHAI/data/rhai_village_scores_B.csv",
    "rhai_tt_A": ROOT / "RHAI/data/rhai_traveltimes.csv",
    "rhai_tt_B": ROOT / "RHAI/data/rhai_traveltimes_scenarioB.csv",
    "rhai_pop": ROOT / "RHAI/data/village_population.csv",
    "swai_pop": ROOT / "SWAI/data/village_population.csv",
    "swai_final": ROOT / "SWAI/data/swai_final.csv",
    "swai_with_district": ROOT / "SWAI/data/swai_with_district.csv",
    "swai_Village_csv": ROOT / "SWAI/data/Village.csv",
    "swai_elevation": ROOT / "SWAI/data/village_elevation_v2.csv",
    "swai_water_distance": ROOT / "SWAI/data/village_water_distance.csv",
}

buf = io.StringIO()


def p(*a):
    print(*a, file=buf)


def load(path):
    if path.suffix == ".gpkg":
        import pyogrio
        layers = pyogrio.list_layers(path)
        p(f"  layers: {[tuple(l) for l in layers]}")
        g = gpd.read_file(path, layer=layers[0][0])
        p(f"  crs: {g.crs}")
        return g
    return pd.read_csv(path, encoding="utf-8")


p(f"python {sys.version.split()[0]}  pandas {pd.__version__}  geopandas {gpd.__version__}")
frames = {}
for key, path in SOURCES.items():
    p("=" * 78)
    p(f"[{key}] {path.relative_to(ROOT)}")
    if not path.exists():
        p("  MISSING")
        continue
    df = load(path)
    frames[key] = df
    p(f"  rows: {len(df)}  cols: {len(df.columns)}")
    p(f"  columns: {list(df.columns)}")
    p("  dtypes: " + ", ".join(f"{c}:{t}" for c, t in df.dtypes.astype(str).items()))
    idcol = "village_id" if "village_id" in df.columns else None
    if idcol:
        s = df[idcol]
        p(f"  village_id: n_unique={s.nunique()}  dup_rows={s.duplicated().sum()}  "
          f"null={s.isna().sum()}  min={s.min()}  max={s.max()}")
    else:
        p("  NO village_id column")
    num = df.select_dtypes("number")
    nonfin = {c: int((~np.isfinite(num[c].to_numpy(dtype=float))).sum()) for c in num.columns}
    nonfin = {c: v for c, v in nonfin.items() if v}
    p(f"  non-finite numeric counts: {nonfin or 'none'}")
    p("  head(2):")
    p("    " + df.drop(columns="geometry", errors="ignore").head(2).to_string().replace("\n", "\n    "))

# ---- Cross-source alignment, keyed on the RHAI A score table ------------------
p("=" * 78)
p("ALIGNMENT vs rhai_scores_A (reference: 5,159 villages)")
ref = frames["rhai_scores_A"].set_index("village_id")
ref_ids = set(ref.index)
for key, df in frames.items():
    if "village_id" not in df.columns or key == "rhai_scores_A":
        continue
    ids = set(df["village_id"])
    p(f"  {key:22s} ref∩={len(ref_ids & ids):5d}  only_ref={len(ref_ids - ids):4d}  "
      f"only_src={len(ids - ref_ids):4d}  only_src_sample={sorted(ids - ref_ids)[:5]}")

# Coordinates: compare X,Y (or geometry) per village_id
p("-" * 78)
p("COORDINATE agreement (max |dX|,|dY| in degrees on shared ids)")
for key, df in frames.items():
    if "village_id" not in df.columns or key == "rhai_scores_A":
        continue
    d = df.drop_duplicates("village_id").set_index("village_id")
    if "X" in d.columns:
        x, y = d["X"], d["Y"]
    elif "geometry" in d.columns:
        gg = gpd.GeoSeries(d.geometry, crs=df.crs).to_crs(4326)
        x, y = gg.x, gg.y
    else:
        continue
    common = ref.index.intersection(d.index)
    dx = (ref.loc[common, "X"] - x.loc[common]).abs()
    dy = (ref.loc[common, "Y"] - y.loc[common]).abs()
    p(f"  {key:22s} n={len(common)}  max_dX={dx.max():.2e}  max_dY={dy.max():.2e}  "
      f"n_mismatch(>1e-6)={int(((dx > 1e-6) | (dy > 1e-6)).sum())}")

# Districts: RHAI district vs SWAI spatial-join district
p("-" * 78)
p("DISTRICT agreement RHAI(A) vs SWAI(with_district)")
sw = frames["swai_with_district"].set_index("village_id")
common = ref.index.intersection(sw.index)
a, b = ref.loc[common, "district"].astype(str), sw.loc[common, "district"].astype(str)
mism = (a != b)
p(f"  shared={len(common)}  mismatched={int(mism.sum())}")
if mism.any():
    p("  top mismatch pairs (RHAI -> SWAI):")
    p("    " + pd.crosstab(a[mism], b[mism]).stack().loc[lambda s: s > 0]
      .sort_values(ascending=False).head(25).to_string().replace("\n", "\n    "))
p(f"  RHAI districts ({ref['district'].nunique()}): {sorted(ref['district'].unique())}")
p(f"  SWAI districts ({sw['district'].nunique()}): {sorted(sw['district'].astype(str).unique())}")

# Population: RHAI scores population vs RHAI/SWAI pop files vs SWAI pop_sum
p("-" * 78)
p("POPULATION agreement (max abs diff on shared ids)")
for key, col in [("rhai_pop", "pop_sum"), ("swai_pop", "pop_sum"), ("swai_final", "pop_sum"),
                 ("rhai_scores_B", "population")]:
    d = frames[key].drop_duplicates("village_id").set_index("village_id")[col]
    c = ref.index.intersection(d.index)
    diff = (ref.loc[c, "population"] - d.loc[c]).abs()
    p(f"  {key:22s} n={len(c)}  max_abs_diff={diff.max():.4g}  "
      f"n_diff>1e-3={int((diff > 1e-3).sum())}  ref_null={int(ref['population'].isna().sum())}")

# A vs B: identical village sets / districts?
p("-" * 78)
B = frames["rhai_scores_B"].set_index("village_id")
c = ref.index.intersection(B.index)
p(f"A vs B: shared={len(c)}  district_mismatch={int((ref.loc[c,'district'] != B.loc[c,'district']).sum())}")
for col in ["min_any", "min_primary"]:
    p(f"  {col}: A null={int(ref[col].isna().sum())}  B null={int(B[col].isna().sum())}  "
      f"A>=B share={(ref.loc[c,col] >= B.loc[c,col] - 1e-9).mean():.4f}  "
      f"A max={ref[col].max():.1f}  B max={B[col].max():.1f}")
p(f"  access_band A: {ref['access_band'].value_counts(dropna=False).to_dict()}")
p(f"  access_band B: {B['access_band'].value_counts(dropna=False).to_dict()}")

# Duplicates in water distance detail
wd = frames.get("swai_water_distance")
if wd is not None:
    dups = wd[wd["village_id"].duplicated(keep=False)].sort_values("village_id")
    p("-" * 78)
    p(f"swai_water_distance duplicated rows: {len(dups)} (ids {dups['village_id'].nunique()})")
    p("    " + dups.head(6).to_string().replace("\n", "\n    "))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(buf.getvalue(), encoding="utf-8")
print(f"wrote {OUT}")
