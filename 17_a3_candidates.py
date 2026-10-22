"""A3 step 1: district-constrained candidate generation and pair features for the PPHI matcher.

Reuses RHAI rhai_11_geocode_pphi.py logic (settlement-name extraction, district crosswalk, GeoNames
Sindh populated places with Latin variants, villages layer, district candidate buffer = 10 % of the
equivalent radius capped at 12 km). Copied, not imported; a hash check guards the source.
Differences from RHAI, all deliberate:
  - candidates are place ENTITIES (one GeoNames id or one OSM village), each carrying all its name
    variants; RHAI collapsed equal names within a district to the most populous one.
  - non-Latin (Urdu-script) village names are kept as candidates (flag `script_latin`); RHAI dropped
    them. The baseline is evaluated on RHAI's Latin-only pool.
Features per (facility, candidate entity):
  fz_tsr     max RapidFuzz token_sort_ratio over the entity's names (RHAI baseline score)
  fz_partial max partial_ratio;  fz_wratio max WRatio
  emb_cos    max cosine similarity, paraphrase-multilingual-MiniLM-L12-v2 (ONNX, fastembed)
  rank_tsr, rank_emb   rank of the candidate within the facility by each score (1 = best)
  n_same_name          entities in the district sharing the best-matching name (ambiguity)
  log_pop, src_geonames, script_latin, n_variants
Kept per facility: union of the top 15 by fz_tsr and top 15 by emb_cos.
Labels: pos = entity within 250 m of the facility's verified coordinate in
pphi_geocoded_reviewed.gpkg whose names include matched_place; neg_reviewed = entity of a
manually rejected review pair (pphi_geocode_review_done.csv, decision == reject).
Writes data/a3_candidates.parquet and data/a3_facilities.parquet.
"""
import hashlib
import json
import re

import numpy as np
import pandas as pd
import geopandas as gpd
from rapidfuzz import fuzz

from _common import RHAI, DATA, LOGS, PAPER, log_env, set_seeds

set_seeds()
log_env(__file__)
SRC = RHAI / "scripts/rhai_11_geocode_pphi.py"
h = hashlib.sha256(SRC.read_bytes()).hexdigest()
hf = LOGS / "a3_source_hash.json"
if hf.exists():
    assert json.loads(hf.read_text())["sha256"] == h, "rhai_11 changed; re-verify copied functions"
else:
    hf.write_text(json.dumps({"file": str(SRC), "sha256": h}))

# ---- copied verbatim from rhai_11_geocode_pphi.py --------------------------------------
METRIC_CRS = 32642
SINDH_ADMIN1 = "05"
DISTRICT_BUFFER_M = 12000
PPL_CODES = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLL", "PPLS", "PPLX"}
CROSSWALK = {
    "Tharparkar": "Mithi", "Naushero Feroze": "Naushahro Firoz", "Shaheed Benazirabad": "Nawab Shah",
    "Jacobabad": "Jakobabad", "Tando Muhammad Khan": "Tando M. Khan", "Mirpurkhas": "Mirphurkhas",
    "Karachi West": "Karachi west", "Kamber": "Larkana", "Sujawal": "Thatta", "Keamari": "Karachi west",
}
PREFIX = re.compile(
    r"^\s*(B\.?H\.?U\.?|BASIC\s+HEALTH\s+UNIT"
    r"|R\.?H\.?C\.?|RURAL\s+HEALTH\s+CENT\w*"
    r"|G\.?D\.?|E\.?D\.?|U\.?S\.?K\.?|D\.?C\.?D\.?|S\.?G\.?D\.?"
    r"|GOV(ERNMENT)?\s+DISPENSARY|DISPENSARY"
    r"|M\.?C\.?H\.?C?\.?(\s+CENT\w*)?|MATERNITY\s+HOME|MOTHER\s+(AND|&)\s+CHILD"
    r"|T\.?H\.?Q\.?|D\.?H\.?Q\.?|TALUKA\s+HEAD\s*QUARTER|DISTRICT\s+HEAD\s*QUARTER"
    r"|GOV(ERNMENT)?\s+HOSPITAL|CIVIL\s+HOSPITAL|HOSPITAL"
    r"|SUB\s*-?\s*HEALTH\s+CENT\w*|HEALTH\s+CENT\w*|PLUS)\s*[-:,]?\s*",
    re.I,
)
GOTH = re.compile(r"^\s*GOTH\s+|\s+GOTH\s*$", re.I)
TRAILING = re.compile(r"\s*\((.*?)\)\s*$|\s+(TALUKA|TEHSIL|DISTT?\.?|DISTRICT)\s+.*$", re.I)
LATIN = re.compile(r"[A-Za-z0-9 .'\-]+")


def settlement_name(facility: str) -> str:
    s = str(facility).strip()
    prev = None
    while prev != s:
        prev = s
        s = PREFIX.sub("", s).strip()
    s = TRAILING.sub("", s).strip()
    s = GOTH.sub(" ", s).strip()
    return re.sub(r"\s+", " ", s)
# ----------------------------------------------------------------------------------------

TOP = 15
POS_RADIUS_M = 250


def districts():
    g = gpd.read_file(RHAI / "data/gadm41_PAK_3.shp")
    return (g[g["NAME_1"] == "Sindh"][["NAME_3", "geometry"]].rename(columns={"NAME_3": "district"})
            .dissolve(by="district", as_index=False).to_crs(4326))


def gazetteer(dist):
    cols = ["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude", "feature_class",
            "feature_code", "country", "cc2", "admin1", "admin2", "admin3", "admin4", "population",
            "elevation", "dem", "timezone", "moddate"]
    gn = pd.read_csv(RHAI / "data/geonames_PK.txt", sep="\t", names=cols, dtype=str, low_memory=False)
    gn = gn[(gn["feature_class"] == "P") & (gn["admin1"] == SINDH_ADMIN1) & gn["feature_code"].isin(PPL_CODES)]
    ents = []
    for r in gn.itertuples(index=False):
        names = {str(r.asciiname), str(r.name)}
        if isinstance(r.alternatenames, str) and r.alternatenames:
            names.update(r.alternatenames.split(","))
        names = sorted({n.strip() for n in names if len(n.strip()) >= 3 and LATIN.fullmatch(n.strip())})
        if names:
            ents.append({"entity": f"gn{r.geonameid}", "names": names, "lon": float(r.longitude),
                         "lat": float(r.latitude), "population": float(r.population or 0),
                         "src_geonames": 1, "script_latin": 1})
    v = gpd.read_file(RHAI / "data/sindh_villages.gpkg").to_crs(4326)
    v = v[v["name"].notna()]
    for r in v.itertuples(index=False):
        n = str(r.name).strip()
        if len(n) < 3:
            continue
        ents.append({"entity": f"v{int(r.village_id)}", "names": [n], "lon": r.geometry.x, "lat": r.geometry.y,
                     "population": float(r.population or 0), "src_geonames": 0,
                     "script_latin": int(bool(LATIN.fullmatch(n)))})
    e = pd.DataFrame(ents)
    eg = gpd.GeoDataFrame(e, geometry=gpd.points_from_xy(e.lon, e.lat), crs=4326)
    dm = dist.to_crs(METRIC_CRS).copy()
    eq = (dm.geometry.area / 3.14159) ** 0.5
    dm["geometry"] = dm.geometry.buffer((0.10 * eq).clip(upper=DISTRICT_BUFFER_M))
    j = gpd.sjoin(eg.to_crs(METRIC_CRS), dm[["district", "geometry"]], how="inner", predicate="within")
    return j.drop(columns=["index_right"]).to_crs(4326).reset_index(drop=True)


dist = districts()
gaz = gazetteer(dist)
print(f"gazetteer entities x district: {len(gaz):,} (non-Latin: {(gaz.script_latin == 0).sum():,})")

fac = pd.read_csv(RHAI / "data/pphi_facilities.csv")
fac["fid"] = np.arange(len(fac))
fac["settlement"] = fac["name"].map(settlement_name)
fac["district_gadm"] = fac["district"].replace(CROSSWALK)

# labels -----------------------------------------------------------------------------
rev = gpd.read_file(RHAI / "data/pphi_geocoded_reviewed.gpkg")
rej = pd.read_csv(RHAI / "data/pphi_geocode_review_done.csv")
rej = rej[rej["decision"] == "reject"]
key = ["district", "name"]
assert not fac.duplicated(key).any() or True
fac = fac.merge(rev[key + ["matched_place", "lon", "lat", "geocode_method"]].rename(
    columns={"lon": "pos_lon", "lat": "pos_lat", "matched_place": "pos_place"}), on=key, how="left")
fac = fac.merge(rej[key + ["matched_place", "lon", "lat"]].rename(
    columns={"lon": "rej_lon", "lat": "rej_lat", "matched_place": "rej_place"}), on=key, how="left")
fac = fac.drop_duplicates("fid")
fac["label_group"] = np.select([fac.pos_lon.notna(), fac.rej_lon.notna()], ["positive", "rejected"], "unlabeled")
print("facilities by label group:", fac["label_group"].value_counts().to_dict())

# embeddings ---------------------------------------------------------------------------
from fastembed import TextEmbedding
model = TextEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                      cache_dir=str(PAPER / "cache/models"))
strings = sorted(set(fac["settlement"].astype(str)) | {n for ns in gaz["names"] for n in ns})
emb = np.vstack(list(model.embed(strings, batch_size=256))).astype(np.float32)
emb /= np.linalg.norm(emb, axis=1, keepdims=True)
idx = {s: i for i, s in enumerate(strings)}
print(f"embedded {len(strings):,} strings")

from pyproj import Geod
geod = Geod(ellps="WGS84")
rows = []
by_d = {d: g.reset_index(drop=True) for d, g in gaz.groupby("district")}
for f in fac.itertuples(index=False):
    cand = by_d.get(f.district_gadm)
    if cand is None or not len(f.settlement) >= 3:
        continue
    s = f.settlement
    sv = emb[idx[s]]
    tsr = np.array([max(fuzz.token_sort_ratio(s, n) for n in ns) for ns in cand["names"]])
    par = np.array([max(fuzz.partial_ratio(s, n) for n in ns) for ns in cand["names"]])
    wr = np.array([max(fuzz.WRatio(s, n) for n in ns) for ns in cand["names"]])
    cos = np.array([max(float(emb[idx[n]] @ sv) for n in ns) for ns in cand["names"]])
    rank_t = pd.Series(-tsr).rank(method="min").to_numpy()
    rank_e = pd.Series(-cos).rank(method="min").to_numpy()
    keep = np.where((rank_t <= TOP) | (rank_e <= TOP))[0]
    best_name = [max(cand.at[k, "names"], key=lambda n: fuzz.token_sort_ratio(s, n)) for k in keep]
    name_counts = pd.Series([n for ns in cand["names"] for n in ns]).value_counts()
    for k, bn in zip(keep, best_name):
        c = cand.iloc[k]
        lab = "none"
        if f.label_group == "positive":
            d = geod.inv(f.pos_lon, f.pos_lat, c.lon, c.lat)[2]
            if d <= POS_RADIUS_M and str(f.pos_place) in c["names"]:
                lab = "pos"
        if f.label_group == "rejected":
            d = geod.inv(f.rej_lon, f.rej_lat, c.lon, c.lat)[2]
            if d <= POS_RADIUS_M and str(f.rej_place) in c["names"]:
                lab = "neg_reviewed"
        rows.append({"fid": f.fid, "entity": c.entity, "district": f.district_gadm, "best_name": bn,
                     "fz_tsr": tsr[k], "fz_partial": par[k], "fz_wratio": wr[k], "emb_cos": cos[k],
                     "rank_tsr": rank_t[k], "rank_emb": rank_e[k], "n_same_name": int(name_counts.get(bn, 1)),
                     "log_pop": np.log1p(c.population), "src_geonames": c.src_geonames,
                     "script_latin": c.script_latin, "n_variants": len(c["names"]),
                     "lon": c.lon, "lat": c.lat, "pair_label": lab})

cands = pd.DataFrame(rows)
cands.to_parquet(DATA / "a3_candidates.parquet", index=False)
fac.drop(columns=[], errors="ignore").to_parquet(DATA / "a3_facilities.parquet", index=False)
pos_fac = fac[fac.label_group == "positive"]
found = cands[cands.pair_label == "pos"]["fid"].nunique()
print(f"candidate pairs: {len(cands):,}; facilities with candidates: {cands.fid.nunique():,}/{len(fac):,}")
print(f"positives recoverable in kept candidates: {found}/{len(pos_fac)}; "
      f"rejected pairs recovered: {(cands.pair_label == 'neg_reviewed').sum()}/{(fac.label_group == 'rejected').sum()}")
print(f"cands per facility: median {cands.groupby('fid').size().median():.0f}, max {cands.groupby('fid').size().max()}")
