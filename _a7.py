"""A7 engine: district flood graphs as arrays, facility states, exact incremental reopening.

Definitions follow docs/prereg_A7.md (frozen 2026-10-20):
  - village flood time = min over facility-reachable nodes within 1 km of the village point (decision 6);
    villages with no node within 1 km = "no mapped road access", excluded from objectives;
  - travel direction facility -> village (RHAI), travel_time on edges, one directed CSR per district;
  - "link" = maximal run of consecutive closed road segments through degree-2 nodes, both directions.
Reopening links only shortens distances, so the post-reopening distances are computed EXACTLY by an
incremental Dijkstra seeded from the reopened edges, relaxing only nodes whose distance improves
(standard decrease-only SSSP update). Results are verified against full re-routing in 24_a7_verify.py.
"""
import heapq
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from _common import DATA, VID
import _routing as R

INF = np.inf


@dataclass
class District:
    name: str
    host: str
    nodes: np.ndarray            # osmid per index
    eu: np.ndarray; ev: np.ndarray; ek: np.ndarray; ett: np.ndarray; elen: np.ndarray
    vid: np.ndarray              # village ids
    near: list                   # per village: node indices within 1 km
    no_road: np.ndarray          # per village bool
    inv_near: dict = field(default_factory=dict)   # node idx -> village positions
    snap_node: np.ndarray = None # per village snapped node index (RHAI rule, for checks)


def load_district(dname, host):
    G = R.load_graph(dname, host)
    osm = np.array(list(G.nodes))
    idx = {n: i for i, n in enumerate(osm)}
    rows = [(idx[u], idx[v], k, d["travel_time"], d["length"]) for u, v, k, d in G.edges(keys=True, data=True)]
    eu, ev, ek, ett, elen = (np.array(c) for c in zip(*rows))
    xy = gpd.GeoSeries(gpd.points_from_xy([G.nodes[n]["x"] for n in osm], [G.nodes[n]["y"] for n in osm]), crs=4326).to_crs(32642)
    tree = cKDTree(np.c_[xy.x, xy.y])
    v, _ = R.district_inputs(dname, R.load_facilities("B"))
    vp = v.to_crs(32642)
    near = [np.array(c, dtype=np.int64) for c in tree.query_ball_point(np.c_[vp.geometry.x, vp.geometry.y], 1000)]
    D = District(dname, host, osm, eu, ev, ek.astype(np.int64), ett.astype(float), elen.astype(float),
                 v[VID].to_numpy(), near, np.array([len(c) == 0 for c in near]))
    for i, c in enumerate(near):
        for n in c:
            D.inv_near.setdefault(int(n), []).append(i)
    D.snap_node = np.array([idx[n] for n in R.ox.distance.nearest_nodes(G, v.geometry.x.to_numpy(), v.geometry.y.to_numpy())])
    D._G = G
    return D


def edge_keys(D):
    return list(zip(D.nodes[D.eu], D.nodes[D.ev], D.ek))


def closed_mask(D, closed_set):
    ks = edge_keys(D)
    return np.array([k in closed_set for k in ks])


def csr(D, open_mask):
    """Directed CSR with the minimum travel time over parallel open edges."""
    n = len(D.nodes)
    df = pd.DataFrame({"u": D.eu[open_mask], "v": D.ev[open_mask], "t": D.ett[open_mask]})
    df = df.groupby(["u", "v"], as_index=False)["t"].min()
    return csr_matrix((df.t.to_numpy() + 1e-9, (df.u.to_numpy(), df.v.to_numpy())), shape=(n, n))  # +1e-9: keep 0-time edges


def node_dist(M, sources):
    if len(sources) == 0:
        return np.full(M.shape[0], INF)
    return dijkstra(M, directed=True, indices=np.unique(sources), min_only=True)


def village_times(D, d):
    """Minutes; inf if no reachable node within 1 km; nan for no-road villages."""
    t = np.array([d[c].min() if len(c) else np.nan for c in D.near]) / 60.0
    return t


def build_links(D, closed):
    """Group closed directed edges into links (maximal chains through degree-2 nodes)."""
    und = {}
    for i in np.nonzero(closed)[0]:
        a, b = sorted((int(D.eu[i]), int(D.ev[i])))
        und.setdefault((a, b), []).append(i)
    nbrs = {}
    for a, b in zip(D.eu, D.ev):
        if a != b:
            nbrs.setdefault(int(a), set()).add(int(b)); nbrs.setdefault(int(b), set()).add(int(a))
    seg_at = {}
    for s in und:
        for x in s:
            seg_at.setdefault(x, []).append(s)
    interior = {x for x, segs in seg_at.items() if len(nbrs.get(x, ())) == 2 and len(segs) == 2}
    seen, links = set(), []
    for s in und:
        if s in seen:
            continue
        chain, stack = [], [s]
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c); chain.append(c)
            for x in c:
                if x in interior:
                    stack.extend(t for t in seg_at[x] if t not in seen)
        eids = np.array(sorted(i for c in chain for i in und[c]))
        ends = sorted({x for c in chain for x in c if x not in interior})
        length_km = sum(min(D.elen[i] for i in und[c]) for c in chain) / 1000.0
        links.append({"edges": eids, "ends": ends, "length_km": length_km})
    return links


class State:
    """Facility state on one district under one closure set; supports exact incremental reopening."""

    def __init__(self, D, M_open, sources, t_normal):
        self.D, self.M = D, M_open
        self.d = node_dist(M_open, sources)
        self.indptr, self.indices, self.data = M_open.indptr, M_open.indices, M_open.data
        self.extra = {}                       # u -> list[(v, w)] for reopened edges
        self.t = village_times(D, self.d)     # flood minutes (inf isolated, nan no-road)
        self.t_normal = t_normal              # normal minutes per village (1 km rule)

    def _neighbors(self, u, cand_extra):
        s, e = self.indptr[u], self.indptr[u + 1]
        for j in range(s, e):
            yield self.indices[j], self.data[j]
        for vw in self.extra.get(u, ()):
            yield vw
        for vw in cand_extra.get(u, ()):
            yield vw

    def improve(self, link):
        """Exact new distances if `link` is reopened: dict node -> new distance (only improved nodes)."""
        D, d = self.D, self.d
        cand = {}
        for i in link["edges"]:
            cand.setdefault(int(D.eu[i]), []).append((int(D.ev[i]), float(D.ett[i])))
        new, heap = {}, []
        for u, lst in cand.items():
            du = d[u]
            if np.isfinite(du):
                for v, w in lst:
                    nd = du + w
                    if nd < d[v] and nd < new.get(v, INF):
                        new[v] = nd; heapq.heappush(heap, (nd, v))
        while heap:
            du, u = heapq.heappop(heap)
            if du > new.get(u, INF):
                continue
            for v, w in self._neighbors(u, cand):
                nd = du + w
                if nd < d[v] and nd < new.get(v, INF):
                    new[v] = nd; heapq.heappush(heap, (nd, v))
        return new

    def village_delta(self, new):
        """Villages whose flood time improves: dict village position -> new minutes."""
        out = {}
        for n, dn in new.items():
            for vi in self.D.inv_near.get(n, ()):
                m = dn / 60.0
                if m < out.get(vi, self.t[vi]):
                    out[vi] = m
        return out

    def commit(self, link, new):
        D = self.D
        for i in link["edges"]:
            self.extra.setdefault(int(D.eu[i]), []).append((int(D.ev[i]), float(D.ett[i])))
        for n, dn in new.items():
            self.d[n] = dn
        for vi, m in self.village_delta(new).items():
            self.t[vi] = m


def objective_gain(state, vdelta, w_cov, w_iso, w_ph, T):
    """Gains (positive = better) of a village-time change for the objectives.
    cov: weighted count newly within T min; iso: weight newly reachable; ph: reduction in added person-hours
    among villages reachable normally AND under flood (newly reachable villages ENTER the sum, as defined)."""
    g_cov = g_iso = g_ph = 0.0
    for vi, m in vdelta.items():
        old = state.t[vi]
        if state.D.no_road[vi]:
            continue
        g_cov += w_cov[vi] * (int(m <= T) - int(old <= T))
        if not np.isfinite(old):
            g_iso += w_iso[vi]
        tn = state.t_normal[vi]
        if np.isfinite(tn):
            old_ph = (old - tn) * w_ph[vi] / 60.0 if np.isfinite(old) else 0.0
            g_ph += old_ph - (m - tn) * w_ph[vi] / 60.0
    return g_cov, g_iso, g_ph
