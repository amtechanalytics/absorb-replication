"""Study: language models write the integration that absorbs an acquired organisation's data into an existing
layered pipeline. Stages: prepare (population, gold, reference check; no model calls) -> gen (first replies) ->
eval0 (build, test, score) -> repair1, repair2 (arms A2 and A3: feedback turn, then build, test, score) -> final."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

from rh.cells import FINAL, run_llm_stage
from rh.context import Stage
from rh.util import RUNS, append_jsonl, journal, now_iso, read_jsonl, write_json

from . import env, prompts, spec

MAX_TOKENS = 8000
MIN_PARSE = 0.60
REFTEXT = env.WORK / "reftext"


def real() -> bool:
    """False in dry runs (stand-in vendor): the SQL engine and the data are then replaced by a stub."""
    return os.environ.get("RH_FAKE_VENDOR") != "1" or os.environ.get("ABSORB_REAL") == "1"


def _tasks() -> list:
    kept = None
    if real():
        from . import study
        kept = study.kept_tasks()
    tasks = spec.all_tasks() if kept is None else [tuple(t.split("|")) for t in kept]
    only = os.environ.get("ABSORB_DEV_TASKS")          # development only: comma-separated task ids
    if only:
        tasks = [t for t in tasks if spec.task_id(t) in only.split(",")]
    return tasks


def _meta(task, arm, sample) -> dict:
    kind, f, x = task
    return {"task": spec.task_id(task), "kind": kind, "format": f, "family": spec.FAMILY_OF.get(f, f), "target": x,
            "arm": arm, "sample": sample, "cov": f if kind == "stg" else "wide"}


# ---------------------------------------------------------------- stage: prepare
def prepare(ctx) -> dict:
    out = RUNS / "prepare"
    out.mkdir(parents=True, exist_ok=True)
    if not real():
        m = {"stub": True, "tasks_total": len(spec.all_tasks()), "tasks_kept": len(spec.all_tasks()), "tasks_dropped": 0}
        write_json(RUNS / ctx.mode / "prepare.json", m)
        return m
    from . import refs, study, worlds
    summ = study.prepare(ctx.hb, log=lambda s: journal("PREP", s), population_archive=out / "population.tar.gz")
    st = worlds.state()
    if not st.get("context_written"):
        prompts.build_context(log=lambda s: journal("PREP", s))
        REFTEXT.mkdir(parents=True, exist_ok=True)
        for f in spec.FORMATS:
            con = env.connect(worlds.db(f"w_{f}"), read_only=True)
            for d in spec.FORMAT_DOMAINS[f]:
                (REFTEXT / f"stg__{f}__{d}.sql").write_text(refs.reference_sql(con, f, d))
            con.close()
        for fam in spec.FAMILY_WORLD:
            for p in spec.PRODUCTS:
                (REFTEXT / f"wide__{fam}__{p}.sql").write_text(
                    refs.wide_reference_sql(p, st["family_lists"][fam][p]["extended"]))
        worlds.save_state(context_written=True)
        st = worlds.state()
    # a resumed run on a new machine regenerates the population: it must be the same one, or the replies already
    # evaluated would be mixed with a different gold
    old = out / "state.json"
    if old.exists():
        try:
            was = json.loads(old.read_text())["steps"]["sources"]["info"]["export_hashes"]
        except (KeyError, json.JSONDecodeError):
            was = None
        now = st["steps"]["sources"]["info"]["export_hashes"]
        core = [d + ".csv" for d in spec.DOMAINS if d != "allergies"]   # allergy reaction columns, claim ids and
        if was is not None and any(was.get(k) != now.get(k) for k in core):   # cost totals vary between Synthea runs
            diff = sorted(k for k in core if was.get(k) != now.get(k))
            raise RuntimeError(f"the regenerated population differs from the one this run started with (files: {diff[:5]})")
    # everything a reader of the results needs about the preparation
    for name in ("refcheck.json", "split.json", "state.json"):
        if (env.WORK / name).exists():
            shutil.copyfile(env.WORK / name, out / name)
    if not (out / "reference_solutions").exists():
        shutil.copytree(REFTEXT, out / "reference_solutions")
    if not (out / "prompt_context").exists() and prompts.CTX.exists():
        shutil.copytree(prompts.CTX, out / "prompt_context")
    m = {"stub": False, "tasks_total": summ["tasks_total"], "tasks_kept": summ["tasks_kept"],
         "tasks_dropped": summ["tasks_dropped"], "dropped": summ["dropped"], "seconds": summ["seconds"],
         "engine": st["steps"]["engine"]["info"], "generated": st["steps"]["generate"]["info"],
         "split": st["steps"]["split"]["info"]}
    write_json(RUNS / ctx.mode / "prepare.json", m)
    write_json(out / "summary.json", m)
    return m


def _prepare_check(ctx, m) -> list:
    need = int(os.environ.get("ABSORB_MIN_TASKS", spec.REFCHECK_MIN_TASKS))
    if m.get("tasks_kept", 0) < need:
        return [f"reference check kept {m.get('tasks_kept')} of {m.get('tasks_total')} tasks; at least {need} are required"]
    return []


def _prepare_coverage(ctx, mode) -> list:
    return [{"format": f} for f in spec.FORMATS] + [{"format": "wide"}]


# ---------------------------------------------------------------- stage: gen
def build_gen(ctx) -> list:
    cells = []
    for task in _tasks():
        kind = task[0]
        text = {arm: prompts.task_text(task, "A3" if arm == "A3" else "A1") for arm in spec.ARMS}
        for arm in spec.ARMS:
            for s in range(spec.SAMPLES):
                for m in ctx.cfg.models:
                    base = f"{spec.task_id(task)}|{arm}|s{s}|{m['id']}"
                    cells.append({"cell_id": "gen|" + base, "model": m["id"], "arm": arm, "prefix": prompts.system(kind),
                                  "item": text[arm], "max_tokens": MAX_TOKENS,
                                  "meta": {**_meta(task, arm, s), "base": base, "turn": 0}})
    return cells


def _reply_check(stage_name):
    def check(ctx, metrics) -> list:
        """At least 60 percent of replies parse for every model and arm (judged from 5 replies up)."""
        cnt: dict = {}
        for r in {r["cell_id"]: r for r in read_jsonl(ctx.out(stage_name))}.values():
            if r["status"] in ("ok", "parse_fail"):
                a = cnt.setdefault((r["model"], r.get("arm")), [0, 0])
                a[0] += r["status"] == "ok"
                a[1] += 1
        return [f"{m} / {arm}: {ok} of {n} replies parse (< {MIN_PARSE})" for (m, arm), (ok, n) in sorted(cnt.items())
                if n >= 5 and ok / n < MIN_PARSE]
    return check


# ---------------------------------------------------------------- evaluation of replies
def _stub_result(cell_id: str, meta: dict) -> dict:
    h = int(hashlib.sha1(cell_id.encode()).hexdigest(), 16)
    build = h % 10 < 8 and cell_id != "drill|first"
    tests = build and h % 7 < 5
    exact = tests and h % 3 < 2
    f1 = 1.0 if exact else (0.5 + (h % 40) / 100 if build else 0.0)
    res = {"stub": True, "kind": meta["kind"], "format": meta["format"], "build_ok": build, "tests_ok": tests,
           "exact": exact, "f1": f1, "precision": f1, "recall": f1, "recoverable_cells": 100,
           "correct_cells": int(100 * f1), "extra_rows": 0, "content_stable": build, "key_stable": False if build else None,
           "errors": [] if build else [{"node": "stub", "message": "stub build error"}], "compile_error": None,
           "failed_tests": [] if tests or not build else [{"test": "stub_test", "status": "fail", "failures": 1, "message": ""}],
           "tests_fail": 0 if tests or not build else 1, "tests_pass": 5, "skipped": 0, "contract_diff": []}
    if meta["kind"] == "wide" and build:
        res["wide"] = {"existing_undisturbed": h % 5 < 4, "new_columns_ok": exact, "missing_existing": [],
                       "order_kept": True, "missing_new": [], "unexpected_columns": [], "acquirer_rows_changed": 0,
                       "existing_columns": 10, "new_columns_expected": 2}
    return res


def _evaluate_one(row: dict, mode: str) -> dict:
    meta = row["meta"]
    if row["status"] != "ok":
        res = {"kind": meta["kind"], "format": meta["format"], "no_sql": True, "build_ok": False, "tests_ok": False,
               "reply_status": row["status"]}
        sql = None
    else:
        sql = row["parsed"]["sql"]
        if not real():
            res = _stub_result(row["cell_id"], meta)
        else:
            from . import study
            tag = hashlib.sha1(f"{mode}|{row['cell_id']}".encode()).hexdigest()[:14]
            _kind, f, x = meta["task"].split("|")
            res = (study.evaluate_staging(f, x, sql, tag) if meta["kind"] == "stg" else study.evaluate_wide(f, x, sql, tag))
    needs, fb = prompts.feedback(res)
    return {"cell_id": row["cell_id"], "base": meta["base"], "model": row["model"], "arm": row.get("arm"),
            "turn": meta.get("turn", 0), "meta": meta, "sql": sql, "result": res, "needs_repair": needs, "feedback": fb,
            "ts": now_iso()}


def _evaluate(ctx, src: str, out_name: str) -> dict:
    out = ctx.out(out_name)
    rows = {}
    for r in read_jsonl(ctx.out(src)):
        if r["status"] in FINAL:
            rows[r["cell_id"]] = r
    done = {r["cell_id"] for r in read_jsonl(out)}
    jobs = [r for cid, r in sorted(rows.items()) if cid not in done]
    journal("EVAL", f"{ctx.mode}/{out_name}: {len(rows)} replies, {len(done)} evaluated, {len(jobs)} to evaluate")
    n_workers = 1
    if real():
        from . import study
        n_workers = study.workers(per=3)
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = [ex.submit(_evaluate_one, r, ctx.mode) for r in jobs]
        for i, f in enumerate(as_completed(futs)):
            append_jsonl(out, f.result())
            if ctx.hb is not None:
                ctx.hb.touch()
            if (i + 1) % 25 == 0:
                journal("EVAL", f"{ctx.mode}/{out_name}: {i + 1} of {len(jobs)} evaluated")
    ev = list(read_jsonl(out))
    return {"evaluated": len(ev), "build_ok": sum(1 for r in ev if r["result"].get("build_ok")),
            "tests_ok": sum(1 for r in ev if r["result"].get("tests_ok")),
            "exact": sum(1 for r in ev if r["result"].get("exact")),
            "eval_errors": sum(1 for r in ev if r["result"].get("eval_error")),
            "needs_repair": sum(1 for r in ev if r["needs_repair"])}


def eval0(ctx) -> dict:
    return _evaluate(ctx, "gen", "eval0")


def _eval_check(ctx, m) -> list:
    out = []
    if m.get("evaluated", 0) == 0:
        out.append("nothing was evaluated")
    elif m.get("eval_errors", 0) > 0.05 * m["evaluated"]:
        out.append(f"{m['eval_errors']} of {m['evaluated']} evaluations ended in a harness error")
    return out


# ---------------------------------------------------------------- stages: repair turns
def _repair_cells(ctx, n: int) -> list:
    cells = []
    for r in read_jsonl(ctx.out(f"eval{n - 1}")):
        if r["arm"] not in ("A2", "A3") or not r["needs_repair"]:
            continue
        meta = dict(r["meta"])
        task = tuple(meta["task"].split("|"))
        item = prompts.repair_text(prompts.task_text(task, "A3" if r["arm"] == "A3" else "A1"), r["sql"], r["feedback"])
        meta["turn"] = n
        cells.append({"cell_id": f"rep{n}|{r['base']}", "model": r["model"], "arm": r["arm"],
                      "prefix": prompts.system(meta["kind"]), "item": item, "max_tokens": MAX_TOKENS, "meta": meta})
    return cells


def _repair(n: int):
    def run(ctx) -> dict:
        name = f"rep{n}"
        cells = _repair_cells(ctx, n)
        m = {"repair_cells": len(cells)}
        if cells:
            inner = Stage(name, "llm", build=lambda c: cells, schema=prompts.parse_reply, gate={"min_parse_rate": MIN_PARSE})
            lm = run_llm_stage(ctx, inner)
            m.update({k: lm[k] for k in ("ok", "parse_fail", "vendor_error", "empty_reply")})
            m["reply_fails"] = _reply_check(name)(ctx, lm)
            if lm["vendor_error"] > max(1, 0.01 * lm["cells"]):
                m["reply_fails"].append(f"{lm['vendor_error']} vendor errors in {lm['cells']} repair calls")
            m.update(_evaluate(ctx, name, f"eval{n}"))
        if n == 1 and ctx.mode == "pilot":
            m["drill"] = _drill(ctx)
        return m
    return run


def _repair_check(ctx, m) -> list:
    return list(m.get("reply_fails") or []) + ([f"{m['eval_errors']} repair evaluations ended in a harness error"]
                                               if m.get("eval_errors", 0) > max(2, 0.05 * m.get("evaluated", 0)) else [])


DRILL_SQL = "select patient_ref, concept_cd from {{ source('raw_d1', 'dx_history_typo') }}"


def _drill(ctx) -> dict:
    """Pilot only: every model gets one repair turn on a deliberately broken model, so the repair path (feedback
    text, second call, second build) is exercised even when no first reply needs repair. Not part of any result."""
    tasks = [t for t in _tasks() if t[0] == "stg"]
    task = next((t for t in tasks if t[1] == "d1" and t[2] == "conditions"), tasks[0] if tasks else None)
    if task is None:
        return {"skipped": "no staging task"}
    meta = {**_meta(task, "A2", 0), "base": "drill", "turn": 1}
    first = {"cell_id": "drill|first", "status": "ok", "parsed": {"sql": DRILL_SQL}, "model": "-", "arm": "A2",
             "meta": {**meta, "base": "drill|first", "turn": 0}}
    out0 = ctx.out("drill_first")
    prev = list(read_jsonl(out0))
    if not prev:
        append_jsonl(out0, _evaluate_one(first, ctx.mode))
        prev = list(read_jsonl(out0))
    ev = prev[0]
    item = prompts.repair_text(prompts.task_text(task, "A1"), ev["sql"], ev["feedback"])
    cells = [{"cell_id": f"drill|{m['id']}", "model": m["id"], "arm": "A2", "prefix": prompts.system("stg"), "item": item,
              "max_tokens": MAX_TOKENS, "meta": {**meta, "base": f"drill|{m['id']}"}} for m in ctx.cfg.models]
    inner = Stage("drill", "llm", build=lambda c: cells, schema=prompts.parse_reply, gate={"min_parse_rate": 0.0})
    lm = run_llm_stage(ctx, inner)
    ev2 = _evaluate(ctx, "drill", "drill_eval")
    return {"first_needed_repair": ev["needs_repair"], "replies_ok": lm["ok"], "replies": lm["cells"],
            "rebuilt_ok": ev2["build_ok"], "exact_after_repair": ev2["exact"]}


# ---------------------------------------------------------------- stage: final
KEEP = ("build_ok", "tests_ok", "exact", "precision", "recall", "f1", "recoverable_cells", "correct_cells",
        "candidate_cells", "extra_rows", "all_gold_cells", "correct_all_cells", "content_stable", "key_stable", "wide",
        "no_sql", "stub", "tests_fail", "tests_pass", "models_error", "seconds", "content_changed")


def _compact(res: dict) -> dict:
    c = {k: res[k] for k in KEEP if k in res}
    c["eval_error"] = bool(res.get("eval_error"))
    c["contract_ok"] = not res.get("contract_diff")
    c["silent_wrong"] = bool(res.get("build_ok") and res.get("tests_ok") and not res.get("exact"))
    return c


def final(ctx) -> dict:
    turns = []
    for n in range(spec.MAX_REPAIR_TURNS + 1):
        turns.append({r["base"]: r for r in read_jsonl(ctx.out(f"eval{n}"))})
    out = RUNS / ctx.mode / "final.jsonl"
    out.unlink(missing_ok=True)
    n_rows = 0
    for base, r0 in sorted(turns[0].items()):
        chain = [r0] + [t[base] for t in turns[1:] if base in t]
        last = chain[-1]
        append_jsonl(out, {"base": base, **{k: r0["meta"][k] for k in ("task", "kind", "format", "family", "target", "arm", "sample")},
                           "model": r0["model"], "turns": len(chain), "final": _compact(last["result"]),
                           "by_turn": [_compact(c["result"]) for c in chain]})
        n_rows += 1
    return {"rows": n_rows, "groups": len({(r["model"], r["arm"]) for r in turns[0].values()})}


def _final_check(ctx, m) -> list:
    return [] if m.get("rows", 0) > 0 else ["no final rows"]


STAGES = [
    Stage("prepare", "local", run=prepare, gate={"check": _prepare_check}, coverage=_prepare_coverage),
    Stage("gen", "llm", build=build_gen, schema=prompts.parse_reply,
          gate={"min_parse_rate": MIN_PARSE, "max_duplicate_cells": 0, "check": _reply_check("gen")}),
    Stage("eval0", "local", run=eval0, gate={"check": _eval_check}, coverage="derived"),
    Stage("repair1", "local", run=_repair(1), gate={"check": _repair_check}, coverage="derived"),
    Stage("repair2", "local", run=_repair(2), gate={"check": _repair_check}, coverage="derived"),
    Stage("final", "local", run=final, gate={"check": _final_check}, coverage="derived"),
]


def analyze(ctx) -> None:
    from . import analysis
    analysis.run(ctx)


def brief(ctx) -> list:
    return ["Read results/hypotheses.csv and results/t6_comparisons.csv against the approach.",
            "Dropped tasks and the reference check are in results/prepare/refcheck.json; decisions the run took are in runs/decisions.md.",
            "Rebuild control for generated keys: results/t3_non_regression.csv, rows with scope = control."]


def fake_response(model_id: str, prefix: str, item: str) -> str:
    """Stand-in reply for dry runs. With the engine and the data present it answers with the reference solution,
    a broken variant or a silently wrong variant, so every evaluation path is exercised without a vendor."""
    first = item.split("\n", 1)[0]
    tid = first[6:].strip() if first.startswith("task: ") else ""
    ref = REFTEXT / (tid.replace("|", "__") + ".sql")
    if not (real() and tid and ref.exists()):
        return "```sql\nselect 1 as placeholder\n```"
    sql = ref.read_text()
    if "## Your previous model" in item:
        return "Corrected.\n```sql\n" + sql + "\n```"
    h = int(hashlib.sha1((model_id + item).encode()).hexdigest(), 16) % 10
    if h in (6, 7):
        return "```sql\n" + sql + "\nfrom (\n```"
    if h == 8:
        return "```sql\nselect * from (\n" + sql + "\n) as r where false\n```"
    if h == 9:
        return "I am not able to write this model."
    return "Here is the model.\n```sql\n" + sql + "\n```"
