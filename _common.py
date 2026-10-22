"""Shared paths, seeds and helpers for paper_a scripts. Read-only w.r.t. core-data sources."""
import json
import platform
import random
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path

import numpy as np

PAPER = Path(__file__).resolve().parent
CORE = PAPER.parent
RHAI = CORE / "RHAI"
SWAI = CORE / "SWAI"
FLOOD = CORE / "flood-recovery-sindh"
DATA = PAPER / "data"
TABLES = PAPER / "results" / "tables"
FIGS = PAPER / "results" / "figures"
DOCS = PAPER / "docs"
LOGS = PAPER / "logs"

SEED = 20221001
VID = "village_id"
PKGS = ["numpy", "pandas", "geopandas", "shapely", "pyproj", "pyogrio", "pyarrow",
        "networkx", "osmnx", "scipy", "scikit-learn", "rapidfuzz", "matplotlib"]


def set_seeds(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)


def log_env(script_name):
    """Write package versions + seed for this run to logs/<script>.env.json."""
    LOGS.mkdir(parents=True, exist_ok=True)
    vers = {}
    for p in PKGS:
        try:
            vers[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            vers[p] = None
    info = {"script": script_name, "run_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "seed": SEED, "packages": vers}
    (LOGS / f"{Path(script_name).stem}.env.json").write_text(json.dumps(info, indent=2))
    return info


def wmedian(v, w):
    """Population-weighted median, identical to RHAI rhai_20_final_audit.wmedian."""
    v = np.asarray(v, float); w = np.asarray(w, float)
    o = np.argsort(v); v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


def wquantile(v, w, q):
    """Population-weighted quantile; same convention as wmedian (q=0.5 reproduces it).
    np.inf values are allowed and sort last (used for isolated villages)."""
    v = np.asarray(v, float); w = np.asarray(w, float)
    o = np.argsort(v); v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[min(np.searchsorted(c, c[-1] * q), len(v) - 1)])
