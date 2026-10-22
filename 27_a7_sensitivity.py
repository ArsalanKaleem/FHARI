"""A7 sensitivity collection + H2 bias ratios across configurations.

For every data/a7/<cfg>/ (except length-budget configs) run 26_a7_analysis.py if its tables are missing,
then collect headline regret rows (objectives cov60, iso, ph; K = 20, plus K = 100 for N1000 runs).
Length-budget configs (`_L<km>`): regret of the final allocation per state, same definitions.
H2 (prereg §9): A/B and A/ensemble-mean ratios of (i) coverage shortfall 1 - C60, (ii) isolated people,
(iii) added person-hours, from the A7 no-protection values (K = 0) of each configuration; intervals for
A/ensemble from a bootstrap over draws (2,000). Village-bootstrap intervals exist for the base configs
only (`a2_masks_h2_bootstrap.csv`) — logged deviation.
Writes results/tables/a7_sensitivity_regret.csv and a7_h2_by_config.csv.
"""
import subprocess
import sys

import numpy as np
import pandas as pd

from _common import DATA, TABLES, PAPER, SEED, log_env

log_env(__file__)
rng = np.random.default_rng(SEED)
cfgs = sorted(p.name for p in (DATA / "a7").iterdir() if (p / "values.parquet").exists() and "_N30_" not in p.name)
rows, h2 = [], []
for cfg in cfgs:
    V = pd.read_parquet(DATA / "a7" / cfg / "values.parquet")
    DR = sorted(s for s in V.state.unique() if s.startswith("d"))
    # ---- H2 from K = 0 values ----------------------------------------------------------------
    v0 = V[(V.K == 0) & (V.objective == "cov60") & (V.alloc == "A")].set_index("state")
    for name, col, f in (("cov60_shortfall", "cov60", lambda x: 1 - x), ("isolated_dedup", "iso_dedup", lambda x: x),
                         ("added_ph_dedup", "ph_dedup", lambda x: x)):
        a, b, e = f(v0.loc["A", col]), f(v0.loc["B", col]), f(v0.loc[DR, col].to_numpy())
        boot = [a / e[rng.integers(0, len(e), len(e))].mean() for _ in range(2000)]
        h2.append({"cfg": cfg, "outcome": name, "A": a, "B": b, "ens_mean": e.mean(), "ratio_A_B": a / b if b else np.nan,
                   "ratio_A_ens": a / e.mean() if e.mean() else np.nan,
                   "ratio_A_ens_lo95": np.percentile(boot, 2.5), "ratio_A_ens_hi95": np.percentile(boot, 97.5)})
    # ---- regret -----------------------------------------------------------------------------------
    if "_L" in cfg:
        fin = V.sort_values("K").groupby(["objective", "alloc", "state"]).tail(1)
        for obj, col, sign in (("cov60", "cov60", 1), ("iso", "iso_rhai", -1), ("ph", "ph_dedup", -1)):
            x = fin[fin.objective == obj]
            e0 = V[(V.objective == obj) & (V.K == 0) & (V.alloc == "opt")].set_index("state")[col].loc[DR] * sign
            opt = x[x.alloc == "opt"].set_index("state")[col].loc[DR] * sign
            for al in ("A", "B", "ens"):
                xv = x[x.alloc == al].set_index("state")[col].loc[DR] * sign
                rows.append({"cfg": cfg, "objective": obj, "K": "length", "alloc": al,
                             "regret_share": (opt - xv).mean() / (opt - e0).mean() if (opt - e0).mean() else np.nan,
                             "length_km_mean": x[x.alloc == al]["length_km"].mean()})
        continue
    tab = TABLES / f"a7_{cfg}_regret.csv"
    if not tab.exists():
        subprocess.run([sys.executable, "-B", str(PAPER / "26_a7_analysis.py"), cfg], check=True,
                       stdout=subprocess.DEVNULL, cwd=PAPER)
    r = pd.read_csv(tab)
    ks = [20] + ([100] if "_K100" in cfg else [])
    r = r[r.objective.isin(["cov60", "iso", "ph"]) & r.K.isin(ks) & r.alloc.isin(["A", "B", "ens", "EVPI"])]
    rows += [{"cfg": cfg, **x} for x in r.to_dict("records")]

S = pd.DataFrame(rows); H = pd.DataFrame(h2)
S.to_csv(TABLES / "a7_sensitivity_regret.csv", index=False); H.to_csv(TABLES / "a7_h2_by_config.csv", index=False)
pd.set_option("display.width", 250)
piv = S[S.alloc.isin(["A", "B", "ens"])].pivot_table(index=["cfg", "objective", "K"], columns="alloc", values="regret_share")
print("REGRET SHARE (headline) by configuration:\n" + piv.round(3).to_string())
print("\nH2 ratios:\n" + H.round(3).to_string(index=False))
