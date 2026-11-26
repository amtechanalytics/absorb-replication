"""Recompute every result table and every number quoted in the paper from the stored run records,
and compare them with the files in this repository, byte for byte.

Usage (from the repository root, Python 3.9 or later, standard library only):

    python3 reproduce.py

Checks:
  1. results/*.csv and results/prepare/*  <- paper/analysis.py run on runs/full/final.jsonl and runs/prepare/
  2. analysis/numbers.json                <- analysis/analyse.py run on runs/
  3. runs/prepare/population.tar.gz       <- sha256 recorded in runs/prepare/population.json

Exit code 0 only if every check matches.
"""
import filecmp
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_table_generator(scratch):
    """Import paper/analysis.py (and the two modules it needs) without running the harness package."""
    os.environ["RH_ROOT"] = str(scratch)
    sys.path.insert(0, str(ROOT))
    pkg = types.ModuleType("paper")
    pkg.__path__ = [str(ROOT / "paper")]
    sys.modules["paper"] = pkg
    for name in ("spec", "analysis"):
        spec = importlib.util.spec_from_file_location("paper." + name, ROOT / "paper" / (name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["paper." + name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["paper.analysis"]


def compare_trees(new, old, label, problems):
    n = 0
    for f in sorted(p for p in old.rglob("*") if p.is_file()):
        rel = f.relative_to(old)
        g = new / rel
        n += 1
        if not g.exists():
            problems.append("%s/%s: not produced" % (label, rel))
        elif not filecmp.cmp(f, g, shallow=False):
            problems.append("%s/%s: differs" % (label, rel))
    extra = sorted(str(p.relative_to(new)) for p in new.rglob("*") if p.is_file() and not (old / p.relative_to(new)).exists())
    for e in extra:
        problems.append("%s/%s: produced but not in the repository" % (label, e))
    return n


def main():
    problems = []
    scratch = Path(tempfile.mkdtemp(prefix="reproduce-"))
    try:
        (scratch / "runs").mkdir()
        shutil.copytree(ROOT / "runs" / "full", scratch / "runs" / "full")
        shutil.copytree(ROOT / "runs" / "prepare", scratch / "runs" / "prepare",
                        ignore=shutil.ignore_patterns("population.tar.gz"))
        analysis = load_table_generator(scratch)
        analysis.run(None)
        n = compare_trees(scratch / "results", ROOT / "results", "results", problems)
        print("1. result tables:      %d files compared" % n)

        out = scratch / "numbers.json"
        subprocess.run([sys.executable, str(ROOT / "analysis" / "analyse.py"), str(ROOT), str(out)],
                       check=True, stdout=subprocess.DEVNULL)
        same = filecmp.cmp(out, ROOT / "analysis" / "numbers.json", shallow=False)
        if not same:
            problems.append("analysis/numbers.json: differs")
        print("2. numbers in paper:   analysis/numbers.json %s" % ("identical" if same else "DIFFERS"))

        pop = ROOT / "runs" / "prepare" / "population.tar.gz"
        info = json.loads((ROOT / "runs" / "prepare" / "population.json").read_text())
        if pop.exists():
            h = hashlib.sha256()
            with open(pop, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            ok = h.hexdigest() == info["sha256"]
            if not ok:
                problems.append("runs/prepare/population.tar.gz: sha256 differs from population.json")
            print("3. population archive: sha256 %s" % ("matches" if ok else "DIFFERS"))
        else:
            problems.append("runs/prepare/population.tar.gz: missing")
            print("3. population archive: missing")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if problems:
        print("REPRODUCE FAILED")
        for p in problems:
            print("  " + p)
        return 1
    print("REPRODUCE OK: every table and number matches the stored run records byte for byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
