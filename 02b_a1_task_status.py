"""A1: print the state of the Earth Engine export tasks submitted by 02_a1_flood_masks_gee.py.

Task ids are read from logs/a1_submit.log. States: READY (queued), RUNNING, COMPLETED, FAILED,
CANCELLED. On COMPLETED, download s1_flood_<year>_30m*.tif from Google Drive folder
`paper_a_exports` into paper_a/data/raw/s1_flood/.
"""
import re
import warnings

import ee

from _common import LOGS

warnings.filterwarnings("ignore")
ee.Initialize(project="flood-recovery-sindh")
ids = [i for f in sorted(LOGS.glob("a1*_submit.log"))
       for i in re.findall(r"submitted Drive export (\w+)", f.read_text())]
for t in ids:
    s = ee.data.getTaskStatus(t)[0]
    print(f"{s.get('description', t):24s} {s.get('state'):10s} {s.get('error_message', '')}")
