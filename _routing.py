"""Routing core shared by A2 (flood-conditioned) and A4 (Monte Carlo facility layers).

Reproduces RHAI rhai_05_route_by_district.py / rhai_05b_route_scenarioB.py exactly:
  - villages: sjoin(predicate="within") to the GADM L3 district polygon
  - facilities: polygon centroids (computed in EPSG:32642), filtered to district + 15 km halo;
    if none fall in the halo, ALL facilities are used (RHAI fallback)
  - graph: district drive graph, RHAI speeds, largest weakly connected component
  - snapping: ox.distance.nearest_nodes on the unprojected graph
  - travel time: multi-source Dijkstra on the DIRECTED graph seeded at facility nodes, i.e. time
    FROM facility TO village node (RHAI's direction; on one-way roads this can differ from
    village -> facility). Unreached node -> NaN (= isolated; never capped).
Closures (A2) are applied by deleting edges from a copy of the graph; the largest-component
restriction is NOT re-applied after closure, so villages cut off by flooding become isolated
rather than silently disappearing.
"""
from functools import lru_cache

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from _common import RHAI, PAPER

GRAPHS = PAPER / "cache/graphs"
TIERS = ("primary", "secondary", "tertiary")
HALO_M = 15000
MIRROR_HOSTS = ("overpass.kumi.systems", "overpass-api.de", "maps.mail.ru")


def safe_name(d):
    return d.replace(" ", "_").replace("/", "_")


@lru_cache(maxsize=1)
def districts():
    dist = gpd.read_file(RHAI / "data/gadm41_PAK_3.shp").to_crs(4326)
    namecol = "NAME_3" if "NAME_3" in dist.columns else "NAME_2"
    dist = dist[dist["NAME_1"] == "Sindh"][[namecol, "geometry"]]
    return dist.rename(columns={namecol: "district"})


@lru_cache(maxsize=1)
def villages_all():
    return gpd.read_file(RHAI / "data/sindh_villages.gpkg").to_crs(4326)


def load_facilities(scenario):
    """Scenario 'A' = facilities_tiered.gpkg, 'B' = facilities_merged_final.gpkg (RHAI handling)."""
    if scenario == "A":
        f = gpd.read_file(RHAI / "data/facilities_tiered.gpkg").to_crs(4326)
    elif scenario == "B":
        f = gpd.read_file(RHAI / "data/facilities_merged_final.gpkg").to_crs(4326)
        f = f[[c for c in f.columns if c in ("geometry", "tier", "source", "name")]].copy()
        if "tier" not in f.columns:
            f["tier"] = "unclassified"
        f["tier"] = f["tier"].fillna("unclassified")
    else:
        raise ValueError(scenario)
    f["geometry"] = f.to_crs(32642).geometry.centroid.to_crs(4326)
    return f


def district_inputs(dname, fac_all):
    d = districts()[districts()["district"] == dname]
    v = gpd.sjoin(villages_all(), d, how="inner", predicate="within")
    v = v[[c for c in v.columns if not c.startswith("index_")]]
    fbuf = d.to_crs(32642).buffer(HALO_M).to_crs(4326).union_all()
    f = fac_all[fac_all.geometry.within(fbuf)].copy()
    if len(f) == 0:
        f = fac_all.copy()
    return v, f


def available_graphs(dname):
    s = safe_name(dname)
    return [h for h in MIRROR_HOSTS if (GRAPHS / f"{s}__{h}__edges.parquet").exists()]


def load_graph(dname, host):
    s = safe_name(dname)
    nodes = gpd.read_parquet(GRAPHS / f"{s}__{host}__nodes.parquet")
    edges = gpd.read_parquet(GRAPHS / f"{s}__{host}__edges.parquet").set_index(["u", "v", "key"])
    nodes.index.name = "osmid"
    return ox.graph_from_gdfs(nodes, edges, graph_attrs={"crs": "epsg:4326"})


def snap(G, v, f):
    v = v.copy(); f = f.copy()
    v["node"] = ox.distance.nearest_nodes(G, v.geometry.x.to_numpy(), v.geometry.y.to_numpy())
    f["node"] = ox.distance.nearest_nodes(G, f.geometry.x.to_numpy(), f.geometry.y.to_numpy())
    return v, f


def nearest_min(G, fac_nodes):
    nodes = [n for n in pd.unique(fac_nodes) if n in G]
    if not nodes:
        return {}
    return nx.multi_source_dijkstra_path_length(G, nodes, weight="travel_time")


def route(G, v, f):
    """v, f already snapped (columns 'node', f has 'tier'). Returns DataFrame of minutes (NaN=isolated)."""
    out = pd.DataFrame({"village_id": v["village_id"].to_numpy()})
    tmap = nearest_min(G, f["node"])
    out["min_any"] = [tmap.get(n, np.nan) / 60.0 for n in v["node"]]
    for tier in TIERS:
        sub = f[f["tier"] == tier]
        if len(sub):
            tt = nearest_min(G, sub["node"])
            out[f"min_{tier}"] = [tt.get(n, np.nan) / 60.0 for n in v["node"]]
    return out


def close_edges(G, edge_keys):
    """Copy of G with the given (u, v, key) edges removed."""
    H = G.copy()
    H.remove_edges_from([k for k in edge_keys if H.has_edge(*k)])
    return H


def hiding_weight(closed):
    """Dijkstra weight that hides closed (u, v, key) edges; identical to 08_a2_flood_routing.make_weight."""
    if not closed:
        return "travel_time"

    def w(u, v, d):
        best = None
        for k, a in d.items():
            if (u, v, k) in closed:
                continue
            t = a["travel_time"]
            if best is None or t < best:
                best = t
        return best
    return w


def closed_edges(dname, host, data_dir, event, D, T, mask="v1", close_bridges=False, embankment=False):
    """Closed (u, v, key) set for a district under the A2 closure rule (frac_fd_ge{D} >= T)."""
    expo_dir = data_dir / ("segment_exposure" if mask == "v1" else f"segment_exposure_{mask}")
    expo = pd.read_parquet(expo_dir / f"{safe_name(dname)}__{host}.parquet")
    e = pd.read_parquet(GRAPHS / f"{safe_name(dname)}__{host}__edges.parquet")
    if "bridge" in e:                  # same rule as 08_a2_flood_routing.py
        b = e["bridge"].astype(str)
        br = b.str.contains("yes", case=False, na=False) | b.str.lower().isin(["true", "viaduct"])
    else:
        br = False
    expo = expo.merge(e[["u", "v", "key"]].assign(bridge=br), on=["u", "v", "key"], validate="one_to_one")
    m = np.nan_to_num(expo[f"y{event}_frac_fd_ge{D}"].to_numpy(), nan=0.0) >= T
    if not close_bridges:
        m &= ~expo["bridge"].to_numpy(bool)
    if embankment:
        m &= ~expo["highway"].astype(str).str.contains(r"\b(?:trunk|primary)(?:_link)?\b", regex=True).to_numpy()
    return frozenset(map(tuple, expo.loc[m, ["u", "v", "key"]].itertuples(index=False, name=None)))
