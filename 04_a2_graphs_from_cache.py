"""A2 step 1: rebuild RHAI's per-district drive graphs from RHAI's own Overpass cache.

RHAI (rhai_05 / rhai_05b) called ox.graph_from_polygon(district, network_type="drive") with
requests_timeout=300 and rotated three Overpass mirrors; osmnx 2.1.0 cached responses in
RHAI/cache keyed by the full request URL (so each mirror has its own cache entries).

Here, for every district x mirror, we replay the same request with NETWORK ACCESS BLOCKED (dead
proxy), so a graph is built only if every sub-query is a cache hit, i.e. it is exactly the OSM
snapshot RHAI routed on. The RHAI cache is only read (osmnx writes to the cache only after a
successful download, which cannot happen here).

Graphs are post-processed exactly as RHAI did (hwy speeds, travel times, largest weakly
connected component) and saved as nodes/edges GeoParquet under paper_a/cache/graphs/.
Resumable: existing outputs are skipped. Writes results/tables/a2_cache_probe.csv.
"""
import sys
import time
import traceback

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd

from _common import RHAI, PAPER, TABLES, log_env

log_env(__file__)
RHAI_CACHE = r"C:\Projects\RHAI\cache"      # original location (not copied into core-data)
OUT = PAPER / "cache/graphs"
OUT.mkdir(parents=True, exist_ok=True)

# --- identical to rhai_05_route_by_district.py / rhai_05b -------------------------------
MIRRORS = ["https://overpass.kumi.systems/api/interpreter",
           "https://overpass-api.de/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
HWY_SPEEDS = {"motorway": 90, "trunk": 70, "primary": 55, "secondary": 45, "tertiary": 35,
              "unclassified": 25, "residential": 20, "track": 15, "path": 8, "service": 20}
ox.settings.requests_timeout = 300
# ----------------------------------------------------------------------------------------
ox.settings.use_cache = True
ox.settings.cache_folder = RHAI_CACHE
ox.settings.log_console = False
DEAD = "http://127.0.0.1:9"
ox.settings.requests_kwargs = {"proxies": {"http": DEAD, "https": DEAD}, "timeout": 5}

dist = gpd.read_file(RHAI / "data/gadm41_PAK_3.shp").to_crs(4326)
namecol = "NAME_3" if "NAME_3" in dist.columns else "NAME_2"
dist = dist[dist["NAME_1"] == "Sindh"][[namecol, "geometry"]]
districts = sorted(dist[namecol].dropna().unique())
if len(sys.argv) > 1:                       # optional: restrict to named districts
    districts = [d for d in districts if d in sys.argv[1:]]

rows = []
for dname in districts:
    poly = dist[dist[namecol] == dname].union_all()
    safe = dname.replace(" ", "_").replace("/", "_")
    for url in MIRRORS:
        host = url.split("//")[1].split("/")[0]
        e_out = OUT / f"{safe}__{host}__edges.parquet"
        if e_out.exists():
            rows.append({"district": dname, "mirror": host, "hit": True, "note": "already built"})
            continue
        ox.settings.overpass_url = url
        t0 = time.time()
        try:
            G = ox.graph_from_polygon(poly, network_type="drive")
        except Exception as e:
            rows.append({"district": dname, "mirror": host, "hit": False,
                         "note": f"{type(e).__name__}: {str(e)[:80]}"})
            continue
        G = ox.add_edge_speeds(G, hwy_speeds=HWY_SPEEDS)
        G = ox.add_edge_travel_times(G)
        largest = max(nx.weakly_connected_components(G), key=len)
        G = G.subgraph(largest).copy()
        nodes, edges = ox.graph_to_gdfs(G)
        keep = [c for c in ["osmid", "highway", "length", "speed_kph", "travel_time",
                            "oneway", "reversed", "bridge", "name", "geometry"] if c in edges.columns]
        edges = edges[keep].copy()
        for c in edges.columns:
            if c != "geometry" and edges[c].dtype == object:
                edges[c] = edges[c].astype(str)
        nodes[["x", "y", "geometry"]].to_parquet(OUT / f"{safe}__{host}__nodes.parquet")
        edges.reset_index().to_parquet(e_out)
        rows.append({"district": dname, "mirror": host, "hit": True, "n_nodes": len(nodes),
                     "n_edges": len(edges), "secs": round(time.time() - t0, 1)})
        print(f"{dname:16s} {host:28s} HIT  nodes={len(nodes):,} edges={len(edges):,} "
              f"({time.time()-t0:.0f}s)", flush=True)
        del G, nodes, edges
    pd.DataFrame(rows).to_csv(TABLES / "a2_cache_probe.csv", index=False)

probe = pd.DataFrame(rows)
print("\nCache hits per district:")
print(probe.pivot_table(index="district", columns="mirror", values="hit", aggfunc="first").to_string())
