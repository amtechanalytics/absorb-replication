"""Per-task counts of the staging integrations (the appendix table of the paper), from results/cells.csv.

Usage: python3 analysis/per_task.py [results/cells.csv]
Prints one line per task: format, domain, recoverable cells, exact in A1, A2, A3 (each of 6),
passing the build and every test (of 18), and silent wrong (passing and not exact).
"""
import collections
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "results", "cells.csv")
ORDER = ["fhir_r4", "fhir_stu3", "claims", "d1", "d2", "d3"]

tasks = collections.defaultdict(collections.Counter)
cells = {}
with open(SRC, newline="") as fh:
    for r in csv.DictReader(fh):
        if r["kind"] != "stg":
            continue
        key = (r["format"], r["target"])
        c = tasks[key]
        c["n"] += 1
        c["exact_" + r["arm"]] += r["exact"] == "True"
        c["pass"] += r["tests_ok"] == "True"
        c["silent"] += r["silent_wrong"] == "True"
        if r["recoverable_cells"]:
            cells[key] = max(cells.get(key, 0), int(r["recoverable_cells"]))

total = collections.Counter()
print("format     domain        cells     A1 A2 A3  pass  silent")
for fmt in ORDER:
    for (f, target) in sorted(k for k in tasks if k[0] == fmt):
        c = tasks[(f, target)]
        print("%-10s %-12s %9d   %2d %2d %2d  %4d  %6d" % (f, target, cells.get((f, target), 0), c["exact_A1"],
              c["exact_A2"], c["exact_A3"], c["pass"], c["silent"]))
        for k in ("n", "exact_A1", "exact_A2", "exact_A3", "pass", "silent"):
            total[k] += c[k]
print("%d tasks, %d integrations: exact %d/%d/%d, pass %d, silent wrong %d" % (len(tasks), total["n"], total["exact_A1"],
      total["exact_A2"], total["exact_A3"], total["pass"], total["silent"]))
