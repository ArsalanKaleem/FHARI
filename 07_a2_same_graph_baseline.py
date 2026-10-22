"""A2: normal-conditions baseline with Scenario A and B routed on the SAME graph per district.

06_a2_reproduce_rhai.py showed RHAI's B reproduces exactly on one cached graph per district
(mostly overpass.kumi.systems) while RHAI's A mostly matches no cached graph, so RHAI's A-vs-B
contrast mixes a facility-layer effect with an OSM-snapshot effect. Here both scenarios are routed
on the graph that reproduces RHAI B (fallback: kumi), so A - B isolates the facility layer.

Malir: verified exact for both A and B on kumi in 06 (and routing it took >1 h on this machine),
so its RHAI values are copied rather than re-routed. Recorded in column `source`.

Writes data/a2_normal_times.parquet (village_id, district, graph, tt_* for A and B, source) and
results/tables/a2_same_graph_vs_rhai.csv.
"""
import numpy as np
import pandas as pd

from _common import RHAI, DATA, TABLES, VID, log_env, set_seeds, wmedian
import _routing as R

set_seeds()
log_env(__file__)
COLS = ["min_any", "min_primary", "min_secondary", "min_tertiary"]
COPY_FROM_RHAI = {"Malir"}
OUT = DATA / "a2_normal_times.parquet"

choice = pd.read_csv(TABLES / "a2_graph_choice.csv").set_index("district")
fac = {s: R.load_facilities(s) for s in ("A", "B")}
parts = []
for dname in sorted(R.districts()["district"].unique()):
    hosts = R.available_graphs(dname)
    if not hosts:
        continue
    b_ok = choice.loc[dname, "B"] if dname in choice.index else np.nan
    host = b_ok.split("|")[0] if isinstance(b_ok, str) else "overpass.kumi.systems"
    if dname in COPY_FROM_RHAI:
        a = pd.read_csv(RHAI / f"data/district_results/{R.safe_name(dname)}.csv")
        b = pd.read_csv(RHAI / f"data/district_results_B/{R.safe_name(dname)}.csv")
        d = a[[VID] + [c for c in COLS if c in a]].add_suffix("_A").rename(columns={f"{VID}_A": VID}).merge(
            b[[VID] + [c for c in COLS if c in b]].add_suffix("_B").rename(columns={f"{VID}_B": VID}), on=VID)
        d["source"] = "rhai_copy_verified_exact"
    else:
        G = R.load_graph(dname, host)
        res = {}
        for s in ("A", "B"):
            v, f = R.district_inputs(dname, fac[s])
            v, f = R.snap(G, v, f)
            res[s] = R.route(G, v, f).set_index(VID).add_suffix(f"_{s}")
        d = res["A"].join(res["B"], how="outer").reset_index()
        d["source"] = "routed"
        del G
    d["district"], d["graph"] = dname, host
    parts.append(d)
    print(f"{dname:16s} {host:24s} n={len(d)}  {d['source'].iloc[0]}", flush=True)

nt = pd.concat(parts, ignore_index=True)
for c in COLS:
    for s in "AB":
        if f"{c}_{s}" not in nt:
            nt[f"{c}_{s}"] = np.nan
assert nt[VID].is_unique and len(nt) == 5159, (len(nt), nt[VID].duplicated().sum())
nt.to_parquet(OUT, index=False)

# ---- compare with RHAI ----------------------------------------------------------------
vm = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "population", "min_any_A", "min_any_B"])
m = vm.merge(nt[[VID, "min_any_A", "min_any_B"]], on=VID, suffixes=("_rhai", "_same"))
rows = []
for s in "AB":
    d = (m[f"min_any_{s}_same"] - m[f"min_any_{s}_rhai"])
    rows += [(f"{s}: villages differing >1e-6 min", int((d.abs() > 1e-6).sum())),
             (f"{s}: max |diff| min", float(d.abs().max())),
             (f"{s}: mean diff (same - rhai) min", float(d.mean())),
             (f"{s}: isolated same-graph", int(m[f"min_any_{s}_same"].isna().sum())),
             (f"{s}: isolated rhai", int(m[f"min_any_{s}_rhai"].isna().sum()))]
for tag in ("rhai", "same"):
    j = m.dropna(subset=[f"min_any_A_{tag}", f"min_any_B_{tag}"])
    wa, wb = wmedian(j[f"min_any_A_{tag}"], j["population"]), wmedian(j[f"min_any_B_{tag}"], j["population"])
    slower = int((j[f"min_any_B_{tag}"] > j[f"min_any_A_{tag}"] + 0.01).sum())
    rows += [(f"{tag}: n", len(j)), (f"{tag}: wmedian A", wa), (f"{tag}: wmedian B", wb),
             (f"{tag}: overstatement x", wa / wb), (f"{tag}: unweighted median A", j[f'min_any_A_{tag}'].median()),
             (f"{tag}: unweighted median B", j[f'min_any_B_{tag}'].median()),
             (f"{tag}: villages slower under B (>0.01)", slower)]
cmp = pd.DataFrame(rows, columns=["metric", "value"])
cmp.to_csv(TABLES / "a2_same_graph_vs_rhai.csv", index=False)
print("\n" + cmp.to_string(index=False))
