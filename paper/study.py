"""Preparation (no model calls): engine, population, gold and comparison worlds, reference check; and the
evaluation of one candidate integration."""
from __future__ import annotations

import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import env, gen, products, refs, score, spec, worlds

PROJDB = env.WORK / "projdb"
REFDIR = env.WORK / "ref"


def pdb(name: str) -> Path:
    PROJDB.mkdir(parents=True, exist_ok=True)
    return PROJDB / f"{name}.duckdb"


def workers(per=4) -> int:
    return max(1, int(os.environ.get("ABSORB_WORKERS", (os.cpu_count() or 2) // per)))


def _step(name, fn, log):
    st = worlds.state()
    if name in st.get("steps", {}):
        return st["steps"][name]
    t0 = time.time()
    out = fn()
    steps = worlds.state().get("steps", {})
    steps[name] = {"seconds": round(time.time() - t0, 1), "info": out}
    worlds.save_state(steps=steps)
    log(f"prepare: {name} done in {steps[name]['seconds']} s; disk free {disk_free_gb()} GB")
    return steps[name]


def _pool(jobs: list, hb, per=4):
    """jobs: list of (label, callable). Runs them in parallel, returns {label: result}; first error is raised."""
    out = {}
    with ThreadPoolExecutor(max_workers=workers(per)) as ex:
        futs = {ex.submit(fn): label for label, fn in jobs}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
            env.touch(hb)
    return out


# ================================================================ preparation
POPULATION_STEPS = ("generate", "split", "sources")


def archive_population(dst: Path) -> dict | None:
    """Synthea 3.0.0 simulates every patient up to the wall-clock time of the run, so a second run of the same
    seed gives a slightly different population. A run therefore keeps the population it generated: the source tables,
    the landed FHIR resources, the claims export and the split go into one archive under runs/, which is backed up
    with the run and restored on a replacement machine instead of generating again."""
    import hashlib
    import tarfile
    if dst.exists():
        return None
    for v in ("fhir_r4", "fhir_stu3"):
        gen._fhir_ndjson(v)
    steps = worlds.state().get("steps", {})
    meta = env.WORK / "population_steps.json"
    meta.write_text(json.dumps({k: steps[k] for k in POPULATION_STEPS}, indent=1, sort_keys=True, default=str))
    members = ["sources", "landing", "split.json", "synthea/out/cpcds", "synthea/generated.json", "population_steps.json"]
    tmp = dst.with_suffix(".part")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tmp, "w:gz", compresslevel=6) as tar:
        for m in members:
            tar.add(env.WORK / m, arcname=m)
    h = hashlib.sha256()
    with open(tmp, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    tmp.replace(dst)
    info = {"file": dst.name, "bytes": dst.stat().st_size, "sha256": h.hexdigest()}
    (dst.parent / "population.json").write_text(json.dumps(info, indent=1, sort_keys=True))
    return info


def restore_population(src: Path, log=print) -> bool:
    """On a machine that has not prepared yet, take the population from the run's archive."""
    import tarfile
    if not src.exists() or "sources" in worlds.state().get("steps", {}):
        return False
    env.WORK.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(env.WORK, filter="data")
    saved = json.loads((env.WORK / "population_steps.json").read_text())
    steps = worlds.state().get("steps", {})
    steps.update({k: saved[k] for k in POPULATION_STEPS})
    worlds.save_state(steps=steps)
    log(f"prepare: population restored from {src.name} (not generated again)")
    return True


def disk_free_gb() -> float:
    env.WORK.mkdir(parents=True, exist_ok=True)
    return round(shutil.disk_usage(env.WORK).free / 1e9, 1)


def prepare(hb=None, log=print, population_archive: Path | None = None) -> dict:
    env.WORK.mkdir(parents=True, exist_ok=True)
    if population_archive is not None:
        restore_population(population_archive, log)
    _step("engine", lambda: {**env.install_engine(hb), **env.versions()}, log)
    _step("generate", lambda: gen.generate(hb), log)
    _step("split", lambda: {k: (len(v) if isinstance(v, list) else v) for k, v in gen.split().items()}, log)
    _step("sources", lambda: {"tables": gen.write_sources(), "export_hashes": gen.sorted_export_hashes()}, log)
    if population_archive is not None:
        info = archive_population(population_archive)
        if info:
            log(f"prepare: population archived ({info['bytes'] / 1e6:.0f} MB, sha256 {info['sha256'][:16]})")
    _step("base", lambda: worlds.build_base(hb), log)

    def gold():
        worlds.copy_db("base", "gold")
        res = worlds.core_build("gold", hb)
        con = env.connect(worlds.db("gold"))
        lists = worlds.category_lists(con)
        con.close()
        worlds.save_state(lists=lists)
        worlds.product_build("gold", {p: lists[p]["extended"] for p in spec.PRODUCTS}, hb)
        score.export_projection(worlds.db("gold"), pdb("gold"))
        return {k: res[k] for k in ("seconds", "models_ok", "tests_pass", "tests_fail", "tests_warn")}

    _step("gold", gold, log)
    lists = worlds.state()["lists"]
    ext = {p: lists[p]["extended"] for p in spec.PRODUCTS}

    def pre(name):
        def run():
            worlds.copy_db("base", name)
            con = env.connect(worlds.db(name))
            gen.restrict_sources(con, "acquirer")
            con.execute("checkpoint")
            con.close()
            res = worlds.core_build(name, hb)
            worlds.product_build(name, {p: lists[p]["existing"] for p in spec.PRODUCTS}, hb)
            score.export_projection(worlds.db(name), pdb(name))
            worlds.drop_world(name)
            return {k: res[k] for k in ("seconds", "models_ok", "tests_pass", "tests_fail")}
        return run

    def et(d):
        def run():
            name = f"et_{d}"
            _proj, res = worlds.downstream_build(name, "gold", None, d, None, ext, hb=hb, test=False)
            worlds.must(res, name)
            score.export_projection(worlds.db(name), pdb(name))
            worlds.drop_world(name)
            return res["seconds"]
        return run

    _step("pre_and_attribution", lambda: _pool(
        [("pre", pre("pre")), ("pre2", pre("pre2"))] + [(f"et_{d}", et(d)) for d in spec.DOMAINS], hb), log)

    def fmt_world(f):
        def run():
            info = worlds.build_format_world(f, ext, hb)
            score.export_projection(worlds.db(f"w_{f}"), pdb(f"w_{f}"))
            return info
        return run

    def gold_claims():
        # the answer for the claims format: the unmodified pipeline on the acquirer's data plus the acquired rows of
        # the four domains a claims export carries (it has no encounters, observations, immunizations or allergies)
        worlds.copy_db("base", "gold_claims")
        con = env.connect(worlds.db("gold_claims"))
        gen.restrict_sources(con, "acquirer", domains=[d for d in spec.DOMAINS if d not in spec.FORMAT_DOMAINS["claims"]])
        con.execute("checkpoint")
        con.close()
        worlds.core_build("gold_claims", hb)
        worlds.product_build("gold_claims", ext, hb, test=False)
        score.export_projection(worlds.db("gold_claims"), pdb("gold_claims"))

        def etc(d):
            def run():
                name = f"etc_{d}"
                _proj, res = worlds.downstream_build(name, "gold_claims", None, d, None, ext, hb=hb, test=False)
                worlds.must(res, name)
                score.export_projection(worlds.db(name), pdb(name))
                worlds.drop_world(name)
                return res["seconds"]
            return run
        out = _pool([(d, etc(d)) for d in spec.FORMAT_DOMAINS["claims"]], hb)
        worlds.drop_world("gold_claims")
        return out

    _step("gold_claims", gold_claims, log)
    _step("format_worlds", lambda: _pool([(f, fmt_world(f)) for f in spec.FORMATS], hb), log)

    def empty(f, d):
        def run():
            name = f"e_{f}_{d}"
            _proj, res = worlds.downstream_build(name, f"w_{f}", f, d, None, ext, hb=hb, test=False)
            worlds.must(res, name)
            score.export_projection(worlds.db(name), pdb(name))
            worlds.drop_world(name)
            return res["seconds"]
        return run

    _step("empty_worlds", lambda: _pool([(f"{f}|{d}", empty(f, d)) for f in spec.FORMATS for d in spec.FORMAT_DOMAINS[f]], hb), log)

    def families():
        out = {}
        for fam, f in spec.FAMILY_WORLD.items():
            con = env.connect(worlds.db(f"w_{f}"), read_only=True)
            fl = worlds.category_lists(con)
            con.close()
            for tag, key in (("wx", "existing"), ("wg", "extended")):
                name = f"{tag}_{fam}"
                worlds.copy_db(f"w_{f}", name)
                con = env.connect(worlds.db(name))
                models = worlds.reference_models(con, f)
                proj = worlds.project(name, worlds.db(name), external=True)
                worlds.write_absorb(proj, con, f, models)
                con.close()
                worlds.must(worlds.product_build(name, {p: fl[p][key] for p in spec.PRODUCTS}, hb, worlds.ABSORB_VARS,
                                                 test=False), name)
                score.export_projection(worlds.db(name), pdb(name), tables=spec.PRODUCTS)
                worlds.drop_world(name)
            out[fam] = fl
        worlds.save_state(family_lists=out)
        return {fam: {p: {"existing": len(v[p]["existing"]), "new": len(v[p]["new"])} for p in spec.PRODUCTS}
                for fam, v in out.items()}

    _step("families", families, log)
    rc = _step("refcheck", refcheck, log)
    _step("controls", controls, log)
    return summary()


def summary() -> dict:
    st = worlds.state()
    rc = st["steps"]["refcheck"]["info"]
    return {"tasks_total": len(spec.all_tasks()), "tasks_kept": len(rc["kept"]), "tasks_dropped": len(rc["dropped"]),
            "dropped": rc["dropped"], "kept": rc["kept"],
            "seconds": {k: v["seconds"] for k, v in st["steps"].items()}}


def kept_tasks() -> list | None:
    st = worlds.state()
    if "refcheck" not in st.get("steps", {}):
        return None
    return st["steps"]["refcheck"]["info"]["kept"]


# ================================================================ reference check
def _attach(con, names: list) -> None:
    for n in names:
        con.execute(f"attach '{pdb(n)}' as {n} (read_only)")


def _open(names: list):
    con = env.connect(":memory:")
    _attach(con, names)
    return con


def gold_names(fmt: str, domain: str) -> tuple[str, str]:
    """(gold projection, gold without the domain's acquired rows) for a format."""
    return ("gold_claims", f"etc_{domain}") if fmt == "claims" else ("gold", f"et_{domain}")


def gold_rows(con, fmt: str, domain: str, table: str) -> tuple[list, list]:
    """Gold rows of acquired patients that domain `domain` is responsible for, and the column names."""
    g, e = gold_names(fmt, domain)
    cols = score.proj_columns(con, g, table)
    return score.contributed(con, g, e, table, cols), cols


def staging_masks(con, fmt: str, domain: str, world: str, empty: str) -> dict:
    """Per scored table: gold rows, masks of cells that `world` reproduces, unpaired rows of `world`."""
    out = {}
    for t, key in spec.SCORED.items():
        if not score.has_table(con, gold_names(fmt, domain)[0], t):
            continue
        g, cols = gold_rows(con, fmt, domain, t)
        c = score.contributed(con, world, empty, t, cols)
        if not g and not c:
            continue
        masks, extra = score.align(g, c, cols, key)
        out[t] = {"cols": cols, "n_gold": len(g), "masks": masks, "extra": extra, "n_cand": len(c)}
    return out


def carried_mask(fmt: str, table: str, cols: list) -> int:
    return score.column_mask(cols, spec.uncarried(table) if fmt == "claims" else set())


def refcheck() -> dict:
    REFDIR.mkdir(parents=True, exist_ok=True)
    kept, dropped, detail = [], [], {}
    for f in spec.FORMATS:
        con = _open(sorted({n for d in spec.FORMAT_DOMAINS[f] for n in gold_names(f, d)}) + [f"w_{f}"]
                    + [f"e_{f}_{d}" for d in spec.FORMAT_DOMAINS[f]])
        for d in spec.FORMAT_DOMAINS[f]:
            tid = spec.task_id(("stg", f, d))
            m = staging_masks(con, f, d, f"w_{f}", f"e_{f}_{d}")
            total = repro = uncarried = extra_cells = 0
            per_table = {}
            for t, r in m.items():
                cm = carried_mask(f, t, r["cols"])
                nc = score.popcount(cm)
                tot = r["n_gold"] * nc
                rep = sum(score.popcount(x & cm) for x in r["masks"])
                total += tot
                repro += rep
                uncarried += r["n_gold"] * (len(r["cols"]) - nc)
                extra_cells += r["extra"] * nc
                per_table[t] = {"gold_rows": r["n_gold"], "gold_cells": tot, "reproduced": rep, "extra_rows": r["extra"]}
            share = (repro / total) if total else 0.0
            (REFDIR / f"{tid.replace('|', '__')}.json").write_text(json.dumps(
                {t: {"cols": r["cols"], "extra": r["extra"],
                     "masks": [x & carried_mask(f, t, r["cols"]) for x in r["masks"]]} for t, r in m.items()}))
            detail[tid] = {"gold_cells": total, "reproduced": repro, "share": round(share, 4), "format_unrecoverable": uncarried,
                           "reference_extra_cells": extra_cells, "tables": per_table}
            ok = total > 0 and share >= spec.REFCHECK_MIN_SHARE
            if ok:
                kept.append(tid)
            else:
                dropped.append({"task": tid, "reason": "no gold cells" if total == 0
                                else f"reference reproduces {share:.3f} of gold cells"})
        con.close()
    for fam in ("fhir", "claims", "dialect"):
        con = _open([f"wg_{fam}", f"wx_{fam}"])
        for p in spec.PRODUCTS:
            tid = spec.task_id(("wide", fam, p))
            n = con.execute(f'select count(*) from wg_{fam}."{p}" where grp=\'acquired\'').fetchone()[0]
            ncols = len(score.proj_columns(con, f"wg_{fam}", p))
            detail[tid] = {"gold_cells": n * ncols, "reproduced": n * ncols, "share": 1.0 if n else 0.0}
            if n:
                kept.append(tid)
            else:
                dropped.append({"task": tid, "reason": "no acquired rows in this family's world"})
        con.close()
    out = {"kept": kept, "dropped": dropped, "detail": detail}
    (env.WORK / "refcheck.json").write_text(json.dumps(out, indent=1))
    return out


def controls() -> dict:
    """Rebuild control: are generated keys and contents of the acquirer's rows the same in two independent builds
    of the pre-acquisition pipeline, and does the gold build change the acquirer's rows?"""
    con = _open(["gold", "pre", "pre2"])
    kh1, kh2, khg = score.keyhashes(con, "pre"), score.keyhashes(con, "pre2"), score.keyhashes(con, "gold")
    out = {}
    for t in spec.SCORED:
        if t not in kh1:
            continue
        out[t] = {"rebuild_content_diff_rows": score.multiset_diff(con, "pre", "pre2", t, "acquirer"),
                  "rebuild_keys_equal": kh1[t] == kh2.get(t),
                  "gold_content_diff_rows": score.multiset_diff(con, "pre", "gold", t, "acquirer"),
                  "gold_keys_equal": kh1[t] == khg.get(t), "acquirer_rows": kh1[t][0]}
    con.close()
    return out


# ================================================================ evaluation of one candidate
def _apply_baseline(res: dict, fmt: str) -> None:
    """Tests that already fail in the format's reference world (the format lacks a domain, e.g. claims carry no
    encounters) are not counted against a candidate; they are listed in results/prepare/state.json."""
    base = set(worlds.state()["steps"]["format_worlds"]["info"][fmt].get("baseline_failed") or [])
    if not base or not res.get("build_ok"):
        return
    mine = [t for t in res.get("failed_tests") or [] if t["test"] not in base]
    res["baseline_failed_tests"] = len((res.get("failed_tests") or [])) - len(mine)
    res["failed_tests"] = mine
    res["tests_fail"] = len(mine)
    res["tests_ok"] = (res.get("compile_error") is None and not mine and res.get("skipped", 0) == 0
                       and res.get("tests_pass", 0) > 0)



def _contract_diff(want: list, got: list) -> list:
    want = [(c.lower(), t) for c, t in want]          # identifiers are case-insensitive in DuckDB
    got = [(c.lower(), t) for c, t in got]
    w, g = dict(want), dict(got)
    out = [f"missing column {c} ({t})" for c, t in want if c not in g]
    out += [f"unexpected column {c}" for c, _ in got if c not in w]
    out += [f"column {c}: type {g[c]}, contract says {t}" for c, t in want if c in g and g[c] != t]
    return out


def evaluate_staging(fmt: str, domain: str, sql: str, tag: str, hb=None) -> dict:
    name = f"c_{tag}"
    lists = worlds.state()["lists"]
    ext = {p: lists[p]["extended"] for p in spec.PRODUCTS}
    out = {"kind": "stg", "format": fmt, "domain": domain}
    try:
        _proj, res = worlds.downstream_build(name, f"w_{fmt}", fmt, domain, sql, ext, hb=hb, external=False,
                                             timeout=1200, threads=int(os.environ.get("ABSORB_DBT_THREADS", "3")))
        _apply_baseline(res, fmt)
        out.update({k: res[k] for k in ("build_ok", "tests_ok", "models_ok", "models_error", "tests_pass", "tests_fail",
                                        "tests_warn", "skipped", "seconds")})
        out["errors"] = res["errors"][:4]
        out["compile_error"] = res["compile_error"]
        out["failed_tests"] = res["failed_tests"][:15]
        con = env.connect(worlds.db(name), read_only=True)
        got = worlds.relation_columns(con, f"stg_acq__{domain}")
        want = worlds.staging_contract(con, domain)
        con.close()
        out["contract_diff"] = _contract_diff(want, got) if got else ["the model did not build, so its columns are unknown"]
        if res["build_ok"]:
            score.export_projection(worlds.db(name), pdb(name))
            out.update(_score_staging(fmt, domain, name))
    except Exception as e:  # noqa: BLE001 — an evaluation error is recorded, never fatal for the run
        out["eval_error"] = f"{type(e).__name__}: {e}"[:600]
        out.setdefault("build_ok", False)
        out.setdefault("tests_ok", False)
    finally:
        worlds.drop_world(name)
        pdb(name).unlink(missing_ok=True)
    return out


def _score_staging(fmt: str, domain: str, name: str) -> dict:
    tid = spec.task_id(("stg", fmt, domain))
    ref = json.loads((REFDIR / f"{tid.replace('|', '__')}.json").read_text())
    con = _open([*gold_names(fmt, domain), f"e_{fmt}_{domain}", "pre", name])
    m = staging_masks(con, fmt, domain, name, f"e_{fmt}_{domain}")
    rec = corr = cand_cells = extra_rows = gold_all = corr_all = 0
    tables = {}
    for t, r in ref.items():
        cols = r["cols"]
        cm = carried_mask(fmt, t, cols)
        mine = dict(m.get(t, {"masks": [0] * len(r["masks"]), "extra": 0, "n_cand": 0}))
        if len(mine["masks"]) != len(r["masks"]):
            raise RuntimeError(f"{t}: gold row count changed between reference check and evaluation")
        # unpaired rows that the reference world has as well (they come from the other domains' reference
        # integrations) are not counted against the candidate
        mine["extra"] = max(0, mine["extra"] - int(r.get("extra", 0)))
        t_rec = sum(score.popcount(x) for x in r["masks"])
        t_cor = sum(score.popcount(x & y) for x, y in zip(mine["masks"], r["masks"]))
        t_paired = sum(score.popcount(y) for x, y in zip(mine["masks"], r["masks"]) if x)
        t_extra = mine["extra"] * score.popcount(cm)
        rec += t_rec
        corr += t_cor
        cand_cells += t_paired + t_extra
        extra_rows += mine["extra"]
        gold_all += len(r["masks"]) * score.popcount(cm)
        corr_all += sum(score.popcount(x & cm) for x in mine["masks"])
        tables[t] = {"recoverable": t_rec, "correct": t_cor, "extra_rows": mine["extra"],
                     "exact": t_cor == t_rec and mine["extra"] == 0}
    for t, r in m.items():          # rows in tables where gold has none for this domain
        if t not in ref:
            extra_rows += r["extra"]
            cand_cells += r["extra"] * len(r["cols"])
            tables[t] = {"recoverable": 0, "correct": 0, "extra_rows": r["extra"], "exact": r["extra"] == 0}
    prec = corr / cand_cells if cand_cells else 0.0
    recall = corr / rec if rec else 0.0
    f1 = 2 * prec * recall / (prec + recall) if prec + recall else 0.0
    kh, khp = score.keyhashes(con, name), score.keyhashes(con, "pre")
    changed, keys_same = {}, True
    for t in spec.SCORED:
        d = score.multiset_diff(con, "pre", name, t, "acquirer")
        if d != 0:
            changed[t] = d
        if t in khp and kh.get(t) != khp[t]:
            keys_same = False
    con.close()
    return {"recoverable_cells": rec, "correct_cells": corr, "candidate_cells": cand_cells, "extra_rows": extra_rows,
            "precision": round(prec, 6), "recall": round(recall, 6), "f1": round(f1, 6),
            "exact": corr == rec and extra_rows == 0, "all_gold_cells": gold_all, "correct_all_cells": corr_all,
            "tables": tables, "content_stable": not changed, "content_changed": changed, "key_stable": keys_same}


def evaluate_wide(fam: str, product: str, sql: str, tag: str, hb=None) -> dict:
    name = f"c_{tag}"
    fmt = spec.FAMILY_WORLD[fam]
    fl = worlds.state()["family_lists"][fam]
    out = {"kind": "wide", "format": fam, "product": product}
    try:
        _proj, res = worlds.product_candidate_build(name, f"w_{fmt}", fmt, product, sql,
                                                    {p: fl[p]["existing"] for p in spec.PRODUCTS}, hb=hb,
                                                    threads=int(os.environ.get("ABSORB_DBT_THREADS", "3")))
        _apply_baseline(res, fmt)
        out.update({k: res[k] for k in ("build_ok", "tests_ok", "models_ok", "models_error", "tests_pass", "tests_fail",
                                        "tests_warn", "skipped", "seconds")})
        out["errors"] = res["errors"][:4]
        out["compile_error"] = res["compile_error"]
        out["failed_tests"] = res["failed_tests"][:15]
        out["contract_diff"] = []
        if res["build_ok"]:
            score.export_projection(worlds.db(name), pdb(name), tables=[product])
            out.update(_score_wide(fam, product, name, fl))
    except Exception as e:  # noqa: BLE001
        out["eval_error"] = f"{type(e).__name__}: {e}"[:600]
        out.setdefault("build_ok", False)
        out.setdefault("tests_ok", False)
    finally:
        worlds.drop_world(name)
        pdb(name).unlink(missing_ok=True)
    return out


def _score_wide(fam: str, product: str, name: str, fl: dict) -> dict:
    con = _open([f"wg_{fam}", f"wx_{fam}", name])
    gcols = score.proj_columns(con, f"wg_{fam}", product)
    xcols = score.proj_columns(con, f"wx_{fam}", product)
    ccols = score.proj_columns(con, name, product) if score.has_table(con, name, product) else []
    key = products.key_columns(product)
    new_cols = [c for c in gcols if c not in xcols]
    missing_existing = [c for c in xcols if c not in ccols]
    order_ok = ccols[: len(xcols)] == xcols
    missing_new = [c for c in new_cols if c not in ccols]
    unexpected = [c for c in ccols if c not in gcols]
    # gold cells for acquired rows, over the gold column list (a column the candidate lacks is all wrong)
    g = score.contributed(con, f"wg_{fam}", "", product, gcols)
    c = score.contributed(con, name, "", product, gcols)
    masks, extra = score.align(g, c, gcols, key)
    present = score.column_mask(gcols, set(gcols) - set(ccols))
    corr = sum(score.popcount(x & present) for x in masks)
    gold_cells = len(g) * len(gcols)
    cand_cells = len(c) * (len(gcols) + len(unexpected))
    # existing columns: same values for the acquirer's rows as before the extension
    common = [x for x in xcols if x in ccols]
    stable_rows = -1
    if set(key) <= set(common):
        a = score.contributed(con, f"wx_{fam}", "", product, common, grp="acquirer")
        b = score.contributed(con, name, "", product, common, grp="acquirer")
        import collections
        ca, cb = collections.Counter(a), collections.Counter(b)
        stable_rows = sum((ca - cb).values()) + sum((cb - ca).values())
    con.close()
    prec = corr / cand_cells if cand_cells else 0.0
    recall = corr / gold_cells if gold_cells else 0.0
    f1 = 2 * prec * recall / (prec + recall) if prec + recall else 0.0
    existing_ok = not missing_existing and order_ok and stable_rows == 0
    return {"recoverable_cells": gold_cells, "correct_cells": corr, "candidate_cells": cand_cells, "extra_rows": extra,
            "precision": round(prec, 6), "recall": round(recall, 6), "f1": round(f1, 6),
            "exact": corr == gold_cells and extra == 0 and not unexpected,
            "wide": {"existing_columns": len(xcols), "new_columns_expected": len(new_cols),
                     "missing_existing": missing_existing[:20], "order_kept": order_ok, "missing_new": missing_new[:20],
                     "unexpected_columns": unexpected[:20], "acquirer_rows_changed": stable_rows,
                     "existing_undisturbed": existing_ok, "new_columns_ok": not missing_new},
            "content_stable": stable_rows == 0 and not missing_existing, "key_stable": None}
