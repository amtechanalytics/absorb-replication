"""Worlds: DuckDB databases holding the pipeline's output for one configuration of the data.

  base      vocabulary + source tables with acquirer and acquired patients (Synthea CSV)
  gold      the unmodified pipeline on base                              (the answer)
  pre       the unmodified pipeline on the acquirer's patients only      (before the acquisition)
  pre2      a second, independent build of pre                           (rebuild control for generated keys)
  et_<d>    gold without the acquired rows of domain d                   (which gold rows d is responsible for)
  w_<fmt>   acquirer in CSV, acquired absorbed from <fmt> by the reference integrations
  e_<fmt>_<d>  w_<fmt> with the integration of d returning no rows
  candidate w_<fmt> with one integration replaced by a model's SQL
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path

from . import dialects, env, gen, products, refs, spec

DBS = env.WORK / "db"
PROJ = env.WORK / "proj"
TPL = env.WORK / "tpl"
STATE = env.WORK / "state.json"
_LOCK = threading.Lock()

REF_MACRO = """{% macro ref() %}
  {%- set name = varargs[-1] -%}
  {%- set domains = var('absorb_domains', []) -%}
  {%- if name.startswith('stg_synthea__') and name[13:] in domains -%}
    {{ return(builtins.ref('stg_absorb__' ~ name[13:])) }}
  {%- elif varargs | length == 2 -%}
    {{ return(builtins.ref(varargs[0], varargs[1], **kwargs)) }}
  {%- else -%}
    {{ return(builtins.ref(varargs[0], **kwargs)) }}
  {%- endif -%}
{% endmacro %}
"""


def state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(**kw) -> dict:
    with _LOCK:
        s = state()
        s.update(kw)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1, sort_keys=True, default=str))
        tmp.replace(STATE)
        return s


def db(name: str) -> Path:
    DBS.mkdir(parents=True, exist_ok=True)
    return DBS / f"{name}.duckdb"


# ---------------------------------------------------------------- dbt project copies
def _profile(db_path: Path, external: bool) -> str:
    settings = "{TimeZone: 'UTC'}" if external else "{TimeZone: 'UTC', enable_external_access: false}"
    return ("synthea_omop_etl:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n"
            f"      path: '{db_path}'\n      schema: {spec.SCHEMA}\n      threads: 4\n      settings: {settings}\n")


def template(with_seeds: bool = False) -> Path:
    """The pinned pipeline plus its three pinned packages; nothing in it is edited."""
    name = "seeded" if with_seeds else "plain"
    dst = TPL / name
    if (dst / "dbt_project.yml").exists():
        return dst
    repo = env.asset("dbt_synthea")
    tmp = TPL / (name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    ignore = shutil.ignore_patterns(".git", ".github", "target", "logs", "dbt_packages", "*.duckdb",
                                    *([] if with_seeds else ["seeds"]))
    shutil.copytree(repo, tmp, ignore=ignore, symlinks=False)
    (tmp / "seeds").mkdir(exist_ok=True)
    pk = tmp / "dbt_packages"
    pk.mkdir()
    for pin, folder in (("dbt_utils", "dbt_utils"), ("dbt_expectations", "dbt_expectations"), ("dbt_date", "dbt_date")):
        shutil.copytree(env.asset(pin), pk / folder, ignore=shutil.ignore_patterns(".git", "integration_tests", "docs"),
                        symlinks=False)
    (tmp / "macros" / "absorb_ref.sql").write_text(REF_MACRO)
    (tmp / "models" / "products").mkdir()
    (tmp / "models" / "absorb").mkdir()
    (tmp / "prof").mkdir()
    tmp.rename(dst)
    return dst


def project(name: str, db_path: Path, *, external: bool, seeds: bool = False) -> Path:
    dst = PROJ / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template(seeds), dst, symlinks=False)
    (dst / "prof" / "profiles.yml").write_text(_profile(db_path, external))
    return dst


def write_products(proj: Path, lists: dict) -> None:
    d = proj / "models" / "products"
    for p in spec.PRODUCTS:
        (d / f"{p}.sql").write_text(products.sql(p, lists[p]))
    (d / "_products.yml").write_text(products.tests_yaml())


def sources_yaml(con, fmt: str) -> str:
    tabs = [r[0] for r in con.execute(f"select table_name from information_schema.tables where "
                                      f"table_schema='raw_{fmt}' order by 1").fetchall()]
    return ("version: 2\n\nsources:\n" + f"  - name: raw_{fmt}\n    schema: raw_{fmt}\n    tables:\n"
            + "".join(f"      - name: {t}\n" for t in tabs))


def write_absorb(proj: Path, con, fmt: str, models: dict) -> None:
    """models: {domain: SQL of stg_acq__<domain>}; every domain gets its union entry point."""
    d = proj / "models" / "absorb"
    (d / "_absorb__sources.yml").write_text(sources_yaml(con, fmt))
    (d / "_absorb__models.yml").write_text(absorb_tests_yaml())
    for dom in spec.DOMAINS:
        (d / f"stg_acq__{dom}.sql").write_text(models[dom])
        (d / f"stg_absorb__{dom}.sql").write_text(
            "{{ config(materialized='view') }}\n"
            f"select * from {{{{ builtins.ref('stg_synthea__{dom}') }}}}\nunion all by name\n"
            f"select * from {{{{ ref('stg_acq__{dom}') }}}}\n")


def empty_model(dom: str) -> str:
    return f"select * from {{{{ builtins.ref('stg_synthea__{dom}') }}}} where false\n"


ABSORB_VARS = json.dumps({"absorb_domains": spec.DOMAINS})


# ---------------------------------------------------------------- running dbt and reading its results
def run_dbt(proj: Path, args: list, *, hb=None, timeout=3600, threads=4) -> dict:
    t0 = time.time()
    code, out = env.dbt(args, proj, timeout=timeout, hb=hb, threads=threads, log=proj / "dbt.log")
    res = {"exit": code, "seconds": round(time.time() - t0, 1), "models_ok": 0, "models_error": 0, "tests_pass": 0,
           "tests_fail": 0, "tests_warn": 0, "skipped": 0, "errors": [], "failed_tests": [], "compile_error": None}
    rr = proj / "target" / "run_results.json"
    if code in (0, 1) and rr.exists():
        try:
            data = json.loads(rr.read_text())
        except json.JSONDecodeError:
            data = {"results": []}
        for r in data.get("results", []):
            uid, st = r.get("unique_id", ""), r.get("status")
            msg = (r.get("message") or "")[:600]
            if uid.startswith("test."):
                if st == "pass":
                    res["tests_pass"] += 1
                elif st == "warn":
                    res["tests_warn"] += 1
                elif st in ("fail", "error"):
                    res["tests_fail"] += 1
                    res["failed_tests"].append({"test": uid.split(".")[-2] if uid.count(".") >= 3 else uid,
                                                "status": st, "failures": r.get("failures"), "message": msg[:240]})
                else:
                    res["skipped"] += 1
            elif uid.startswith(("model.", "seed.")):
                if st == "success":
                    res["models_ok"] += 1
                elif st == "error":
                    res["models_error"] += 1
                    res["errors"].append({"node": uid.split(".")[-1], "message": msg})
                else:
                    res["skipped"] += 1
        if not data.get("results") and code != 0:
            res["compile_error"] = _tail_error(out)
    else:
        res["compile_error"] = _tail_error(out)
    res["build_ok"] = code in (0, 1) and res["compile_error"] is None and res["models_error"] == 0 and res["models_ok"] > 0
    res["tests_ok"] = False
    return res


def run_then_test(proj: Path, select: list | None, vars_json: str | None = None, *, hb=None, timeout=3600,
                  threads=4, test: bool = True) -> dict:
    """dbt run, then dbt test, on the same selection. Tests never stop downstream models from being rebuilt, so a
    table can never be left over from an earlier build. In a world with absorbed domains the staging tests run
    on the union entry points (their copies in models/absorb), not on the acquirer-only staging models."""
    extra = (["--select", *select] if select else []) + (["--vars", vars_json] if vars_json else [])
    res = run_dbt(proj, ["run", *extra], hb=hb, timeout=timeout, threads=threads)
    res["run_seconds"] = res["seconds"]
    if not res["build_ok"] or res["skipped"]:
        res["build_ok"] = False
        res["tests_ok"] = False
        return res
    if not test:
        return res
    excl = (["--exclude", *[f"stg_synthea__{d}" for d in spec.DOMAINS]] if vars_json else [])
    t = run_dbt(proj, ["test", *extra, *excl], hb=hb, timeout=timeout, threads=threads)
    for k in ("tests_pass", "tests_fail", "tests_warn", "failed_tests"):
        res[k] = t[k]
    res["skipped"] = t["skipped"]
    res["seconds"] = round(res["seconds"] + t["seconds"], 1)
    if t["compile_error"]:
        res["compile_error"] = t["compile_error"]
        res["tests_ok"] = False
    else:
        res["tests_ok"] = t["exit"] in (0, 1) and t["tests_fail"] == 0 and t["skipped"] == 0 and t["tests_pass"] > 0
    return res


def absorb_tests_yaml() -> str:
    """The acquirer's own staging tests, copied onto the union entry points."""
    yml = (env.asset("dbt_synthea") / "models" / "staging" / "synthea" / "_synthea__models.yml").read_text()
    blocks = []
    for d in spec.DOMAINS:
        m = re.search(r"  - name: stg_synthea__" + d + r"\n(.*?)(?=\n  - name: |\Z)", yml, re.S)
        if not m:
            raise RuntimeError(f"no test block for stg_synthea__{d}")
        b = m.group(0).replace(f"- name: stg_synthea__{d}", f"- name: stg_absorb__{d}", 1)
        for x in spec.DOMAINS:
            b = re.sub(r"ref\(\s*'stg_synthea__" + x + r"'\s*\)", f"ref('stg_absorb__{x}')", b)
        blocks.append(b.rstrip())
    return "version: 2\n\nmodels:\n" + "\n".join(blocks) + "\n"


def _tail_error(out: str) -> str:
    out = re.sub(r"\x1b\[[0-9;]*m", "", out or "")
    lines = [ln for ln in out.splitlines() if ln.strip() and "Deprecat" not in ln and "deprecat" not in ln]
    keep = [i for i, ln in enumerate(lines) if re.search(r"Error|error|Exception|Parser|Binder|Catalog|Conversion", ln)]
    if keep:
        lines = lines[keep[0]: keep[0] + 25]
    return "\n".join(lines[-25:])[:1800]


def must(res: dict, what: str) -> dict:
    if not res["build_ok"]:
        raise RuntimeError(f"{what}: dbt build failed: {res['errors'][:3] or res['compile_error']}")
    return res


# ---------------------------------------------------------------- base, gold, pre
def build_base(hb=None) -> dict:
    if state().get("base"):
        return state()["base"]
    p = db("base")
    p.unlink(missing_ok=True)
    proj = project("base", p, external=True, seeds=True)
    res = must(run_dbt(proj, ["seed"], hb=hb), "seed")
    con = env.connect(p)
    gen.load_sources(con)
    counts = {t: con.execute(f'select count(*) from {spec.SRC_SCHEMA}."{t}"').fetchone()[0] for t in spec.SOURCE_TABLES}
    con.close()
    info = {"seed_seconds": res["seconds"], "source_rows": counts}
    save_state(base=info)
    return info


def copy_db(src: str, dst: str) -> Path:
    s, d = db(src), db(dst)
    d.unlink(missing_ok=True)
    Path(str(d) + ".wal").unlink(missing_ok=True)
    shutil.copyfile(s, d)
    return d


def core_build(name: str, hb=None) -> dict:
    """Unmodified pipeline, every model and test."""
    proj = project(name, db(name), external=True)
    for p in (proj / "models" / "products", proj / "models" / "absorb"):
        shutil.rmtree(p)
    return must(run_then_test(proj, None, hb=hb), name)


def product_build(name: str, lists: dict, hb=None, vars_json: str | None = None, test=True) -> dict:
    proj = PROJ / name
    (proj / "models" / "products").mkdir(exist_ok=True)
    write_products(proj, lists)
    return must(run_then_test(proj, ["path:models/products"], vars_json, hb=hb, test=test), name + " products")


def category_lists(con) -> dict:
    """Per product: the acquirer's column list and the values only the acquired rows have."""
    out = {}
    for p in spec.PRODUCTS:
        a = products.categories(con, p, "acquirer")
        q = products.categories(con, p, "acquired")
        ex = products.existing_list(p, a)
        new = products.new_list(a, q)
        out[p] = {"existing": ex, "new": new, "extended": ex + new}
    return out


def reference_models(con, fmt: str) -> dict:
    """The authors' integration for every domain of a format; domains the format does not carry return no rows."""
    return {d: (refs.reference_sql(con, fmt, d) if d in spec.FORMAT_DOMAINS[fmt] else empty_model(d)) for d in spec.DOMAINS}


def build_format_world(fmt: str, lists_ext: dict, hb=None) -> dict:
    """w_<fmt>: acquirer rows from CSV, acquired rows through the reference integrations of <fmt>."""
    name = f"w_{fmt}"
    copy_db("base", name)
    con = env.connect(db(name))
    landed = gen.land(con, fmt)          # the dialects are derived from the acquired CSV rows, so land first
    gen.restrict_sources(con, "acquirer", domains=spec.DOMAINS)
    models = reference_models(con, fmt)
    proj = project(name, db(name), external=True)
    write_absorb(proj, con, fmt, models)
    con.execute("checkpoint")
    con.close()
    write_products(proj, lists_ext)
    res = run_then_test(proj, None, ABSORB_VARS, hb=hb)
    must(res, name)
    return {"landed": landed, "build": {k: res[k] for k in ("seconds", "models_ok", "tests_pass", "tests_fail", "tests_warn")},
            "failed_tests": res["failed_tests"][:20], "baseline_failed": sorted(t["test"] for t in res["failed_tests"])}


def downstream_build(name: str, src_world: str, fmt: str | None, domain: str, model_sql: str | None, lists: dict,
                     hb=None, external=True, timeout=1800, threads=4, test=True) -> tuple[Path, dict]:
    """Copy a world and rebuild everything downstream of one domain's staging entry point.
    fmt None: plain gold world with the domain's acquired source rows removed (et_<d>)."""
    copy_db(src_world, name)
    con = env.connect(db(name))
    if fmt is None:
        gen.restrict_sources(con, "acquirer", domains=[domain])
        con.execute("checkpoint")
        con.close()
        proj = project(name, db(name), external=external)
        shutil.rmtree(proj / "models" / "absorb")
        write_products(proj, lists)
        res = run_then_test(proj, [f"stg_synthea__{domain}+"], None, hb=hb, timeout=timeout, threads=threads, test=test)
        return proj, res
    models = reference_models(con, fmt)
    models[domain] = model_sql if model_sql is not None else empty_model(domain)
    proj = project(name, db(name), external=external)
    write_absorb(proj, con, fmt, models)
    con.close()
    write_products(proj, lists)
    res = run_then_test(proj, [f"stg_acq__{domain}+"], ABSORB_VARS, hb=hb, timeout=timeout, threads=threads, test=test)
    return proj, res


def product_candidate_build(name: str, src_world: str, fmt: str, product: str, model_sql: str, lists: dict,
                            hb=None, timeout=900, threads=4) -> tuple[Path, dict]:
    """Copy a format world and rebuild one data product from a candidate's SQL."""
    copy_db(src_world, name)
    con = env.connect(db(name))
    models = reference_models(con, fmt)
    proj = project(name, db(name), external=False)
    write_absorb(proj, con, fmt, models)
    con.close()
    write_products(proj, lists)
    (proj / "models" / "products" / f"{product}.sql").write_text(model_sql)
    res = run_then_test(proj, [f"{product}+"], ABSORB_VARS, hb=hb, timeout=timeout, threads=threads)
    return proj, res


def drop_world(name: str) -> None:
    db(name).unlink(missing_ok=True)
    Path(str(db(name)) + ".wal").unlink(missing_ok=True)
    shutil.rmtree(PROJ / name, ignore_errors=True)


def staging_contract(con, domain: str) -> list:
    """Columns and types of the acquirer's staging model: the contract an integration must meet."""
    return con.execute(f"select column_name, data_type from information_schema.columns where table_schema='{spec.SCHEMA}' "
                       f"and table_name='stg_synthea__{domain}' order by ordinal_position").fetchall()


def relation_columns(con, name: str) -> list:
    return con.execute(f"select column_name, data_type from information_schema.columns where table_schema='{spec.SCHEMA}' "
                       f"and table_name='{name}' order by ordinal_position").fetchall()
