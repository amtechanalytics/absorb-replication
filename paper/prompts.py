"""Prompts: one system text per task family, one task text per task, the fixed hint sheets (arm A3) and the
repair section (arms A2 and A3, turns 2 and 3). Nothing from the gold ever enters a prompt."""
from __future__ import annotations

import json
import re

from . import dialects, env, gen, hints, products, spec, worlds

MAX_CHARS = 36000          # prefix + item; the ledger counts 3 characters per token, so at most 12,000 tokens
BASE_CHARS = 23500
PREV_SQL_CHARS = 9000
FEEDBACK_CHARS = 3000
CTX = env.WORK / "promptctx"

STG_SYSTEM = """You are a data engineer. An acquirer runs a layered dbt pipeline on DuckDB: raw sources, staging models, intermediate models, OMOP CDM tables and wide data products. It has acquired another organisation whose data arrives in a different format. Your job is to write ONE dbt model that brings one domain of the acquired data into the acquirer's staging layer.

Rules
1. The model is called stg_acq__<domain>. Downstream models read the union by column name of the acquirer's staging model stg_synthea__<domain> and your model. Your model must therefore return exactly the columns of the staging contract, with the same names and data types, one row per source record, and with values written by the same conventions as the acquirer's rows (identifiers, codes, dates and times in UTC, text).
2. Read only the acquired raw tables named in the task, written as {{ source('<raw schema>', '<table>') }}. You may also read {{ ref('stg_map__states') }} (columns state_name, state_abbreviation). Do not read stg_synthea__ models, the acquirer's sources or any OMOP table.
3. The engine is DuckDB. Jinja is limited to source() and ref(). One SELECT statement (CTEs allowed), no DDL, no semicolon.
4. Rows that are already in the pipeline must not change. You only add the acquired organisation's rows.
5. Answer with the complete SQL of the model in one ```sql code block. Put nothing after the code block.
"""

WIDE_SYSTEM = """You are a data engineer. An acquirer runs a layered dbt pipeline on DuckDB that ends in wide data products: tables with one row per person (or person and year) and one column per category value. The column list of each product is written out in its SQL. The acquirer has absorbed the data of an acquired organisation: the acquired patients' rows are now in the OMOP tables the product reads. Your job is to extend ONE product model so that it also covers the category values that only the acquired data has.

Rules
1. Keep every existing column: same name, same position, same expression. Rows of existing patients must keep their values.
2. Add one column for each category value that occurs in the acquired data and that the acquirer's data never had. Do not add columns for values the acquirer already had, whether or not the product has a column for them.
3. Put the new columns after the existing ones, in ascending text order of their standard code, and name them by the product's naming rule.
4. If the acquired data brings no new category value for this product, return the model unchanged.
5. The engine is DuckDB. Keep the {{ ref('...') }} calls of the model. One SELECT statement (CTEs allowed), no DDL, no semicolon.
6. Answer with the complete SQL of the model in one ```sql code block. Put nothing after the code block.
"""

PLACEHOLDER = "(the task details are filled in when the study data has been generated)"


def system(kind: str) -> str:
    return STG_SYSTEM if kind == "stg" else WIDE_SYSTEM


def _clip(s: str, n: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 12] + " …[cut]"


def _json_paths(o, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            _json_paths(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(o, list):
        for v in o:
            _json_paths(v, prefix + "[]", out)
    else:
        out.setdefault(prefix, o)
    return out


def _table_section(con, schema: str, table: str, budget: int) -> str:
    cols = con.execute(f"select column_name, data_type from information_schema.columns where table_schema='{schema}' "
                       f"and table_name='{table}' order by ordinal_position").fetchall()
    n = con.execute(f'select count(*) from {schema}."{table}"').fetchone()[0]
    head = f"### {schema}.{table} ({n} rows)\n"
    if [c for c, _ in cols] == ["id", "resource"]:
        rows = [r[0] for r in con.execute(f'select resource from {schema}."{table}" order by id limit 300').fetchall()]
        if not rows:
            return head + "columns: id VARCHAR, resource JSON (one FHIR resource per row). The table is empty.\n"
        objs = [json.loads(r) for r in rows]
        by_len = sorted(range(len(rows)), key=lambda i: (len(rows[i]), i))
        picks = [by_len[len(by_len) // 2], by_len[-1]] if len(rows) > 1 else [0]
        prof: dict = {}
        ex: dict = {}
        for o in objs:
            p = _json_paths(o)
            for k, v in p.items():
                prof[k] = prof.get(k, 0) + 1
                ex.setdefault(k, v)
        lines = [f"  {k}  ({100 * c // len(objs)}% of resources)  e.g. {_clip(json.dumps(ex[k]), 48)}" for k, c in sorted(prof.items())]
        per = max(600, (budget - 400) // 4)
        txt = (head + "columns: id VARCHAR, resource JSON (one FHIR resource per row)\n"
               + "example resources:\n" + "\n".join(_clip(rows[i], per) for i in picks) + "\n"
               + f"JSON paths seen in the first {len(objs)} resources ([] marks an array):\n" + "\n".join(lines) + "\n")
        return _clip(txt, budget)
    stats = con.execute("select " + ", ".join(f'count("{c}"), min("{c}")::varchar' for c, _ in cols)
                        + f' from {schema}."{table}"').fetchone() if cols else []
    lines = []
    for i, (c, t) in enumerate(cols):
        share = (100 * stats[2 * i] // n) if n else 0
        if share == 0 and len(cols) > 40:
            continue
        lines.append(f'  "{c}" {t}  ({share}% filled)  e.g. {_clip(stats[2 * i + 1], 40)}')
    omitted = len(cols) - len(lines)
    samples = con.execute(f'select * from {schema}."{table}" order by all limit 400').fetchall()
    pick = [samples[0], samples[len(samples) // 2], samples[-1]] if len(samples) >= 3 else samples
    names = [c for c, _ in cols]
    srows = [json.dumps({k: _clip(v, 60) for k, v in zip(names, r) if v is not None}, default=str) for r in pick]
    txt = (head + "columns:\n" + "\n".join(lines) + "\n"
           + (f"  ({omitted} further columns are empty in every row and not listed)\n" if omitted else "")
           + "example rows (empty fields left out):\n" + "\n".join(srows) + "\n")
    return _clip(txt, budget)


def raw_tables(fmt: str, domain: str) -> list:
    if fmt in ("fhir_r4", "fhir_stu3"):
        base = {"patients": ["patient"], "encounters": ["encounter", "providers"], "conditions": ["condition"],
                "procedures": ["procedure", "condition"], "medications": ["medicationrequest", "medication", "condition"],
                "observations": ["observation"], "immunizations": ["immunization"],
                "allergies": ["allergyintolerance", "encounter"]}
        return base[domain]
    if fmt == "claims":
        return ["members"] if domain == "patients" else ["claims"]
    return dialects.source_tables(fmt, domain)


def build_context(log=print) -> None:
    """Everything a prompt needs from the data, written once per run to work/promptctx/<task>.json."""
    CTX.mkdir(parents=True, exist_ok=True)
    repo = env.asset("dbt_synthea")
    yml = (repo / "models" / "staging" / "synthea" / "_synthea__models.yml").read_text()
    for f in spec.FORMATS:
        con = env.connect(worlds.db(f"w_{f}"), read_only=True)
        for d in spec.FORMAT_DOMAINS[f]:
            tid = spec.task_id(("stg", f, d))
            contract = worlds.staging_contract(con, d)
            m = re.search(r"  - name: stg_synthea__" + d + r"\n(.*?)(?=\n  - name: |\Z)", yml, re.S)
            src_rows = con.execute(f'select * from {spec.SRC_SCHEMA}."{d}" order by all limit 300').fetchall()
            names = [c for c, _ in dialects.columns(con, d)]
            pick = [src_rows[0], src_rows[len(src_rows) // 2], src_rows[-1]] if len(src_rows) >= 3 else src_rows
            tabs = raw_tables(f, d)
            per = max(2500, 13000 // len(tabs))
            ctx = {
                "contract": [f"{c} {t}" for c, t in contract],
                "staging_sql": (repo / "models" / "staging" / "synthea" / f"stg_synthea__{d}.sql").read_text().strip(),
                "staging_yml": _clip(m.group(0) if m else "", 2600),
                "acquirer_rows": [json.dumps({k: v for k, v in zip(names, r) if v is not None}, default=str) for r in pick],
                "tables": [_table_section(con, f"raw_{f}", t, per) for t in tabs],
                "hint": hints.staging_hint(con, f, d),
            }
            (CTX / f"{tid.replace('|', '__')}.json").write_text(json.dumps(ctx))
        con.close()
    st = worlds.state()
    for fam, f in spec.FAMILY_WORLD.items():
        fl = st["family_lists"][fam]
        con = env.connect(worlds.db(f"w_{f}"), read_only=True)
        for p in spec.PRODUCTS:
            tid = spec.task_id(("wide", fam, p))
            acq = products.categories(con, p, "acquired")
            known = products.categories(con, p, "acquirer")
            inv = hints.inventory(con, fam, p, acq, known)
            ctx = {"model_sql": products.sql(p, fl[p]["existing"]), "naming": hints.NAMING[p],
                   "inventory": inv["text"], "hint": inv["hint"]}
            (CTX / f"{tid.replace('|', '__')}.json").write_text(json.dumps(ctx))
        con.close()
    log(f"prompt context written for {len(list(CTX.glob('*.json')))} tasks")


def _ctx(tid: str):
    p = CTX / f"{tid.replace('|', '__')}.json"
    return json.loads(p.read_text()) if p.exists() else None


def task_text(task: tuple, arm: str) -> str:
    """The task part of a first-turn prompt (identical for A1 and A2; A3 adds the hint sheet)."""
    tid = spec.task_id(task)
    ctx = _ctx(tid)
    kind, f, x = task
    if ctx is None:
        return f"task: {tid}\n\n{PLACEHOLDER}\n"
    if kind == "stg":
        parts = [f"task: {tid}",
                 f"## Write the model stg_acq__{x}",
                 f"Domain: {x}. Acquired data format: {hints.FORMAT_NAME[f]}. Raw schema: raw_{f}.",
                 "## Staging contract (columns and types your model must return)",
                 "\n".join(ctx["contract"]),
                 f"## The acquirer's staging model stg_synthea__{x} (it reads the acquirer's own CSV source; shown for its conventions)",
                 "```sql\n" + ctx["staging_sql"] + "\n```",
                 "## Its documented columns and tests", ctx["staging_yml"],
                 "## Three rows of the acquirer's source table that this staging model reads",
                 "\n".join(ctx["acquirer_rows"]),
                 "## Acquired raw tables you may read"] + ctx["tables"]
    else:
        parts = [f"task: {tid}",
                 f"## Extend the product model {x}",
                 f"The acquired organisation's data arrived as: {hints.FAMILY_NAME[f]}.",
                 "## Naming rule for columns", ctx["naming"],
                 "## The product model today",
                 "```sql\n" + ctx["model_sql"] + "\n```",
                 "## Category values in the acquired data", ctx["inventory"]]
    text = "\n".join(parts) + "\n"
    hint = ("\n## Mapping hints\n" + ctx["hint"] + "\n") if arm == "A3" else ""
    return _clip(text, BASE_CHARS - len(hint)) + hint


def repair_text(base_item: str, prev_sql: str | None, feedback: str) -> str:
    sec = ("\n## Your previous model\n```sql\n" + _clip(prev_sql or "(no SQL model could be read from your reply)", PREV_SQL_CHARS)
           + "\n```\n## What happened when it was built and tested\n" + _clip(feedback, FEEDBACK_CHARS)
           + "\nCorrect the model. Answer with the complete SQL in one ```sql code block.\n")
    room = MAX_CHARS - len(STG_SYSTEM) - len(sec) - 50
    return _clip(base_item, room) + sec


def feedback(res: dict) -> tuple[bool, str]:
    """(needs repair, text) from an evaluation: build errors, failed tests and the contract diff. Scores against
    the gold are never included."""
    lines = []
    if res.get("no_sql"):
        lines.append("Your reply did not contain a SQL model in a ```sql code block (or it was cut off).")
    if res.get("compile_error"):
        lines.append("dbt could not compile or run the project:\n" + _clip(res["compile_error"], 1400))
    for e in res.get("errors") or []:
        lines.append(f"Model {e['node']} failed: {_clip(e['message'], 600)}")
    if res.get("eval_error") and not lines:
        lines.append("The build did not finish: " + _clip(res["eval_error"], 300))
    ft = res.get("failed_tests") or []
    if ft:
        lines.append(f"{res.get('tests_fail', len(ft))} dbt tests failed, {res.get('tests_pass', 0)} passed. Failed tests:")
        lines += [f"- {t['test']} ({t['status']}, {t.get('failures')} failing rows) {_clip(t.get('message') or '', 160)}" for t in ft[:12]]
    if res.get("skipped"):
        lines.append(f"{res['skipped']} downstream models or tests were skipped because something upstream failed.")
    cd = res.get("contract_diff") or []
    if cd and res.get("kind") == "stg":
        lines.append("Staging contract differences:\n" + "\n".join("- " + c for c in cd[:25]))
    w = res.get("wide")
    if w and (w["missing_existing"] or not w["order_kept"]):
        lines.append("Existing columns of the product: " + (f"missing {w['missing_existing']}; " if w["missing_existing"] else "")
                     + ("" if w["order_kept"] else "their order or position changed."))
    return bool(lines), ("\n".join(lines) if lines else "The model built and every test passed.")


SQL_BLOCK = re.compile(r"```(?:sql|SQL)?[ \t]*\n(.*?)```", re.S)


def parse_reply(text: str) -> dict:
    """The stage schema: the last fenced SQL block of a reply (or a bare SELECT)."""
    blocks = SQL_BLOCK.findall(text or "")
    sql = blocks[-1] if blocks else None
    if sql is None:
        t = (text or "").strip()
        if re.match(r"(?is)^(with|select|--|\{\{|\{#)", t):
            sql = t
    if sql is None:
        raise ValueError("no SQL code block in the reply")
    sql = sql.strip().rstrip(";").strip()
    if not re.search(r"(?i)\bselect\b", sql):
        raise ValueError("the code block holds no SELECT")
    if len(sql) > 60000:
        raise ValueError("SQL longer than 60,000 characters")
    return {"sql": sql}
