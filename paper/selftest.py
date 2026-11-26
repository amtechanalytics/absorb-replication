"""Check of the real evaluation path without any vendor: every kept task's reference solution is evaluated as if
it were a model's reply and must come out exact; three altered variants (does not build, builds but returns no
rows, breaks the contract) must be scored as such.

    ABSORB_ENGINE=system python -m paper.selftest            # all kept tasks
    ABSORB_ENGINE=system python -m paper.selftest stg d1     # only task ids containing every given word

Needs the engine (paper/manifest/engine-requirements.txt), Java and the pinned downloads (ABSORB_ASSET_*, or a
finished datacheck), and a finished preparation (it runs it when missing)."""
from __future__ import annotations

import json
import sys
import time

from . import REFTEXT, env, prompts, spec, study, worlds


def main(words: list) -> int:
    study.prepare(log=lambda s: print(s, flush=True))
    st = worlds.state()
    if not st.get("context_written"):
        from . import prepare as stage_prepare

        class Ctx:
            hb = None
            mode = "selftest"
        stage_prepare(Ctx())
    kept = [tuple(t.split("|")) for t in study.kept_tasks()]
    kept = [t for t in kept if all(w in spec.task_id(t) for w in words)]
    bad = 0
    rows = []
    for i, (kind, f, x) in enumerate(kept):
        ref = (REFTEXT / f"{kind}__{f}__{x}.sql").read_text()
        t0 = time.time()
        res = study.evaluate_staging(f, x, ref, f"st{i}") if kind == "stg" else study.evaluate_wide(f, x, ref, f"st{i}")
        ok = bool(res.get("build_ok") and res.get("tests_ok") and res.get("exact") and res.get("content_stable")
                  and not prompts.feedback(res)[0])
        bad += not ok
        rows.append({"task": spec.task_id((kind, f, x)), "ok": ok, "seconds": round(time.time() - t0, 1),
                     **{k: res.get(k) for k in ("build_ok", "tests_ok", "exact", "precision", "recall", "recoverable_cells",
                                                "extra_rows", "content_stable", "key_stable", "tests_fail", "eval_error")}})
        print(json.dumps(rows[-1]), flush=True)
    variants = []
    stg = next((t for t in kept if t[0] == "stg"), None)
    if stg:
        _k, f, x = stg
        ref = (REFTEXT / f"stg__{f}__{x}.sql").read_text()
        r1 = study.evaluate_staging(f, x, ref + "\nfrom (", "stv1")
        r2 = study.evaluate_staging(f, x, "select * from (\n" + ref + "\n) as r where false", "stv2")
        r3 = study.evaluate_staging(f, x, "select 1 as not_in_the_contract", "stv3")
        variants = [("syntax error", not r1["build_ok"] and prompts.feedback(r1)[0]),
                    ("no rows", bool(r2["build_ok"] and not r2["exact"] and r2["recall"] == 0.0)),
                    ("contract broken", bool(not r3.get("exact") and prompts.feedback(r3)[0]))]
        for name, ok in variants:
            bad += not ok
            print(json.dumps({"variant": name, "ok": ok}), flush=True)
    (env.WORK / "selftest.json").write_text(json.dumps({"references": rows, "variants": variants}, indent=1))
    print(f"SELFTEST {'PASS' if not bad else 'FAIL'}: {len(rows)} references, {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
