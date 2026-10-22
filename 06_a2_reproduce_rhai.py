"""A2 acceptance check: with ZERO closed edges, reproduce RHAI per-district travel times.

For every district, every cached graph version (mirror), and both scenarios (A, B), route with
_routing.py and compare to RHAI's own per-district outputs:
  A -> RHAI/data/district_results/<district>.csv
  B -> RHAI/data/district_results_B/<district>.csv
Columns compared: min_any, min_primary, min_secondary, min_tertiary (NaN must match NaN).

Tolerance: |diff| <= 1e-6 min (float noise only). A district/scenario "reproduces" if every
village matches on every column. The matching graph version per scenario is recorded and is the
one A2 must use for that scenario.

Writes results/tables/a2_reproduction.csv (one row per district x graph x scenario) and
results/tables/a2_graph_choice.csv.
"""
import sys
import time

import numpy as np
import pandas as pd

from _common import RHAI, TABLES, log_env, set_seeds
import _routing as R

set_seeds()
log_env(__file__)
TOL = 1e-6
COLS = ["min_any", "min_primary", "min_secondary", "min_tertiary"]
REF_DIR = {"A": RHAI / "data/district_results", "B": RHAI / "data/district_results_B"}

fac = {s: R.load_facilities(s) for s in ("A", "B")}
print(f"facilities A={len(fac['A']):,}  B={len(fac['B']):,}")
names = sorted(R.districts()["district"].unique())
if len(sys.argv) > 1:
    names = [d for d in names if d in sys.argv[1:]]

rows = []
for dname in names:
    hosts = R.available_graphs(dname)
    refs = {}
    for s in ("A", "B"):
        p = REF_DIR[s] / f"{R.safe_name(dname)}.csv"
        refs[s] = pd.read_csv(p) if p.exists() else None
    if not hosts:
        n_ref = {s: (0 if refs[s] is None else len(refs[s])) for s in refs}
        rows.append({"district": dname, "graph": None, "scenario": "-", "note": f"no graph; RHAI rows {n_ref}"})
        print(f"{dname:16s} no graph (RHAI rows {n_ref})")
        continue
    for host in hosts:
        t0 = time.time()
        G = R.load_graph(dname, host)
        for s in ("A", "B"):
            v, f = R.district_inputs(dname, fac[s])
            v, f = R.snap(G, v, f)
            ours = R.route(G, v, f)
            ref = refs[s]
            row = {"district": dname, "graph": host, "scenario": s, "n_villages": len(ours),
                   "n_ref": None if ref is None else len(ref), "n_fac_in_range": len(f)}
            if ref is not None:
                m = ref.merge(ours, on="village_id", how="outer", suffixes=("_ref", "_ours"),
                              indicator=True)
                row["id_mismatch"] = int((m["_merge"] != "both").sum())
                ok_all = row["id_mismatch"] == 0
                for c in COLS:
                    a = m.get(f"{c}_ref"); b = m.get(f"{c}_ours")
                    if a is None and b is None:
                        continue
                    if a is None or b is None:
                        row[f"{c}_bad"] = len(m); ok_all = False; continue
                    both_nan = a.isna() & b.isna()
                    close = (a - b).abs() <= TOL
                    bad = ~(both_nan | close)
                    row[f"{c}_bad"] = int(bad.sum())
                    row[f"{c}_maxabs"] = float((a - b).abs().max()) if (~both_nan).any() else 0.0
                    ok_all &= not bad.any()
                row["reproduces"] = bool(ok_all)
            rows.append(row)
        print(f"{dname:16s} {host:24s} " + "  ".join(
            f"{r['scenario']}:{'OK' if r.get('reproduces') else 'diff(' + str(r.get('min_any_bad')) + ')'}"
            for r in rows[-2:]) + f"  ({time.time()-t0:.0f}s)", flush=True)
        del G

res = pd.DataFrame(rows)
TABLES.mkdir(parents=True, exist_ok=True)
res.to_csv(TABLES / "a2_reproduction.csv", index=False)
ok = res[res.get("reproduces", False) == True]
choice = (ok.groupby(["district", "scenario"])["graph"].apply(lambda s: "|".join(s)).unstack())
choice.to_csv(TABLES / "a2_graph_choice.csv")
print("\nGraph versions that reproduce RHAI exactly:\n" + choice.to_string())
missing = {(d, s) for d in res.loc[res["graph"].notna(), "district"].unique() for s in "AB"} - \
          set(map(tuple, ok[["district", "scenario"]].to_numpy()))
print(f"\ndistrict x scenario NOT reproduced by any graph: {sorted(missing) or 'none'}")
