"""Regenerate every Paper A table, figure, audit file, dataset and rendered manuscript, in order.

Usage (from paper_a/, with the paper_a venv):
  python make_all.py                 # full local pipeline (skips network / external-input steps)
  python make_all.py --final         # only final products: analysis tables, figures, audit, dataset, manuscript
  python make_all.py --from 25       # start at script number 25
  python make_all.py --network       # also run Earth Engine / download steps (needs authentication; see notes)
  python make_all.py --external      # also run steps needing inputs outside core-data (Geofabrik extract)
  python make_all.py --list          # print the plan only

Notes
- Many steps are resumable and SKIP outputs that already exist (per district / per draw / per stage). To
  regenerate a step from scratch, delete its output folder first (see each script's docstring).
- Earth Engine steps (02, 16) only SUBMIT exports; the GeoTIFFs must be downloaded from Google Drive into
  data/raw/s1_flood/ by hand before steps 03+ can run on new data.
- Full pipeline runtime on the original machine: roughly 3-4 h (A2 ~15 min per mask, A4 ~25 min, A7 ~70 min
  for 14 configurations, A6 ~17 min). Each step's runtime is logged to logs/make_all.log.
Stops at the first failing step (non-zero exit).
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
A7_CONFIGS = [[], ["--event", "2025"], ["--embankment"], ["--close-bridges"], ["--N", "1000", "--Kmax", "100"],
              ["--length-km", "27.975"]] + \
             [["--D", str(D), "--T", str(T)] for D in (1, 3, 5) for T in (0.3, 0.6, 0.9) if (D, T) != (3, 0.6)]
# (number, script, args, tag) — tag: "" local, "net" network/EE, "ext" external inputs, "final" final products
STEPS = [
    (0, "00_phase0_inspect.py", [], ""),
    (1, "01_build_village_master.py", [], ""),
    (2, "02_a1_flood_masks_gee.py", ["--submit"], "net"),
    (3, "03_a1_agreement_check.py", [], ""),
    (4, "04_a2_graphs_from_cache.py", [], ""),
    (5, "05_a1_segment_exposure.py", [], ""),
    (5, "05_a1_segment_exposure.py", ["--mask", "v2"], ""),
    (6, "06_a2_reproduce_rhai.py", [], ""),
    (7, "07_a2_same_graph_baseline.py", [], ""),
    (8, "08_a2_flood_routing.py", [], ""),
    (8, "08_a2_flood_routing.py", ["--mask", "v2"], ""),
    (9, "09_a2_summarize.py", [], ""),
    (10, "10_check_districts_h1.py", [], ""),
    (11, "11_check_population_overlap.py", [], ""),
    (12, "12_check_snapping_canals.py", [], ""),
    (13, "13_check_flood_validation_dw.py", ["--submit"], "net"),
    (14, "14_check_shared_graph.py", [], ""),
    (15, "15_check_spotcheck_imagery.py", [], "net"),
    (16, "16_a1_dryseason_gee.py", ["--submit"], "net"),
    (17, "17_a3_candidates.py", [], ""),
    (18, "18_a3_matcher.py", [], ""),
    (19, "19_a2_dadu_geofabrik.py", ["geofabrik"], "ext"),
    (19, "19_a2_dadu_geofabrik.py", ["cached"], "ext"),
    (20, "20_a1a2_compare_masks.py", [], ""),
    (21, "21_a4_ensemble.py", ["--tag", "base", "--draws", "50"], ""),
    (21, "21_a4_ensemble.py", ["--tag", "q0x0.5", "--draws", "30"], ""),
    (21, "21_a4_ensemble.py", ["--tag", "q0x2", "--draws", "30"], ""),
    (22, "22_a4_summarize.py", [], ""),
    (24, "24_a7_verify.py", [], ""),
] + [(25, "25_a7_run.py", c, "") for c in A7_CONFIGS] + [
    (26, "26_a7_analysis.py", ["2022_D3_T0.6_N200_K50"], "final"),
    (27, "27_a7_sensitivity.py", [], "final"),
    (28, "28_a6_terrain_download.py", [], "net"),
    (29, "29_a6_segments.py", [], ""),
    (30, "30_a6_model.py", [], ""),
    (31, "31_figures.py", [], "final"),
    (32, "32_audit_numbers.py", [], "final"),
    (33, "33_zenodo_dataset.py", [], "final"),
    (34, "34_render_manuscript.py", [], "final"),
    (36, "36_paper_text.py", [], "final"),     # full Natural Hazards text -> docs/paper/paper.json
]
# After step 36 (not a Python script): node manuscript_build/build_docx.js -> docs/paper/NatHaz_manuscript.docx,
# then export to PDF from Microsoft Word (File > Save As > PDF, or Word COM ExportAsFixedFormat).

ap = argparse.ArgumentParser()
ap.add_argument("--final", action="store_true"); ap.add_argument("--from", dest="start", type=int, default=0)
ap.add_argument("--network", action="store_true"); ap.add_argument("--external", action="store_true")
ap.add_argument("--list", action="store_true")
args = ap.parse_args()
plan = []
for n, script, a, tag in STEPS:
    if n < args.start or (args.final and tag != "final") or (tag == "net" and not args.network) \
            or (tag == "ext" and not args.external):
        continue
    if not (HERE / script).exists():
        print(f"[{n:02d}] {script}: not present in this copy, skipped")
        continue
    plan.append((n, script, a))
log = HERE / "logs" / "make_all.log"; log.parent.mkdir(exist_ok=True)
with log.open("a", encoding="utf-8") as L:
    L.write(f"\n=== make_all {datetime.now().isoformat(timespec='seconds')} args={vars(args)} ===\n")
    for n, script, a in plan:
        line = f"[{n:02d}] {script} {' '.join(a)}".rstrip()
        if args.list:
            print(line); continue
        t0 = time.time()
        r = subprocess.run([PY, "-B", script, *a], cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
        dt = time.time() - t0
        status = "OK" if r.returncode == 0 else f"FAILED ({r.returncode})"
        print(f"{line:70s} {status:12s} {dt:7.0f}s", flush=True)
        L.write(f"{line} | {status} | {dt:.0f}s\n")
        if r.returncode != 0:
            L.write(r.stdout[-3000:] + "\n" + r.stderr[-3000:] + "\n")
            print(r.stderr[-2000:]); sys.exit(r.returncode)
print("done" if not args.list else f"{len(plan)} steps")
