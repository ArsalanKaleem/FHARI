"""A7 engine verification (must pass before any A7 result is produced).

1. Engine flood village times (layer B, 2022 base, v1) == A2 08 outputs: r = 0 (snapped node) and
   r = 1 km columns, within 1e-6 min.
2. For 40 random links per district: incremental reopening == full re-route with that link reopened.
3. Five links committed sequentially == full re-route with all five reopened.
Districts: Dadu, Larkana, Sukkur (largest closure sets among routed village districts).
"""
import time

import numpy as np
import pandas as pd

from _common import DATA, VID, SEED, log_env
import _routing as R
import _a7 as E

log_env(__file__)
rng = np.random.default_rng(SEED)
nt = pd.read_parquet(DATA / "a2_normal_times.parquet").set_index(VID)
for dname in ("Dadu", "Larkana", "Sukkur"):
    t0 = time.time()
    host = nt.loc[nt.district == dname, "graph"].iloc[0]
    D = E.load_district(dname, host)
    closed = E.closed_mask(D, R.closed_edges(dname, host, DATA, "2022", 3, 0.6))
    M = E.csr(D, ~closed)
    _, f = R.district_inputs(dname, R.load_facilities("B"))
    src = np.array([np.nonzero(D.nodes == n)[0][0] for n in R.ox.distance.nearest_nodes(
        D._G, f.geometry.x.to_numpy(), f.geometry.y.to_numpy())])
    S = E.State(D, M, src, None)
    a2 = pd.read_parquet(DATA / f"a2_flood/{R.safe_name(dname)}.parquet")
    a2 = a2[(a2.event == "2022") & (a2.D == 3) & (a2["T"] == 0.6) & (a2.scenario == "B")].set_index(VID)
    r0 = S.d[D.snap_node] / 60
    for name, ours, ref in (("r0", r0, a2.loc[D.vid, "min_any"].to_numpy()),
                            ("r1km", S.t, a2.loc[D.vid, "min_any_r1000"].to_numpy())):
        o = np.where(np.isinf(ours), np.nan, ours)
        bad = ~(np.isclose(o, ref, atol=1e-6, equal_nan=True))
        assert not bad.any(), f"{dname} {name}: {bad.sum()} villages differ (max {np.nanmax(np.abs(o - ref)):.6f})"
    links = E.build_links(D, closed)
    sample = rng.choice(len(links), size=min(40, len(links)), replace=False)
    for li in sample:
        lk = links[li]
        new = S.improve(lk)
        vd = S.village_delta(new)
        om = (~closed); om[lk["edges"]] = True
        full = E.village_times(D, E.node_dist(E.csr(D, om), src))
        inc = S.t.copy()
        for vi, m in vd.items():
            inc[vi] = m
        assert np.allclose(np.nan_to_num(inc, nan=-1, posinf=1e9), np.nan_to_num(full, nan=-1, posinf=1e9), atol=1e-6), \
            f"{dname} link {li}: incremental != full"
    # sequential commits
    S2 = E.State(D, M, src, None)
    pick = rng.choice(len(links), size=min(5, len(links)), replace=False)
    om = ~closed
    for li in pick:
        new = S2.improve(links[li]); S2.commit(links[li], new); om[links[li]["edges"]] = True
    full = E.village_times(D, E.node_dist(E.csr(D, om), src))
    assert np.allclose(np.nan_to_num(S2.t, nan=-1, posinf=1e9), np.nan_to_num(full, nan=-1, posinf=1e9), atol=1e-6)
    sizes = pd.Series([len(l["edges"]) for l in links])
    print(f"{dname}: PASS  closed edges {closed.sum():,} -> {len(links):,} links "
          f"(edges/link median {sizes.median():.0f}, max {sizes.max()}); {time.time()-t0:.0f}s", flush=True)
print("ENGINE VERIFIED")
