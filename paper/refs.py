"""Reference solutions (written by the authors), one per task.

A staging reference has two parts: a mapping from the acquired format back to the columns of the pipeline's
source table (paper/refsql/<format>/<domain>.sql, or generated from the dialect definition), followed by the
acquirer's own staging logic copied from the pinned pipeline, so that both organisations' rows are typed and
named by the same rules. A wide-product reference is the product's definition for the extended column list."""
from __future__ import annotations

import re

from . import dialects, env, products, spec

REFSQL = env.HERE / "refsql"


def source_shape_sql(con, fmt: str, domain: str) -> str:
    if fmt in ("d1", "d2", "d3"):
        return dialects.inverse_sql(con, fmt, domain)
    return (REFSQL / fmt / f"{domain}.sql").read_text()


def staging_logic(domain: str) -> str:
    """The acquirer's staging model with its source swapped for the CTE acq_src."""
    path = env.asset("dbt_synthea") / "models" / "staging" / "synthea" / f"stg_synthea__{domain}.sql"
    text = path.read_text()
    text = re.sub(r"\{%\s*set column_names\s*=.*?%\}", "", text, count=1, flags=re.S)
    text, n1 = re.subn(r"\{\{\s*lowercase_columns\(column_names\)\s*\}\}", "*", text)
    text, n2 = re.subn(r"\{\{\s*source\(\s*'synthea'\s*,\s*'" + domain + r"'\s*\)\s*\}\}", "acq_src", text)
    if n1 != 1 or n2 != 1 or not re.match(r"\s*WITH\s", text):
        raise RuntimeError(f"staging model of {domain} does not have the expected shape ({n1}, {n2})")
    return text.strip()


def reference_sql(con, fmt: str, domain: str) -> str:
    cols = dialects.columns(con, domain)
    casts = "\n        , ".join(f'cast(inv."{c}" as {ty}) as "{c}"' for c, ty in cols)
    inner = source_shape_sql(con, fmt, domain).strip().rstrip(";")
    logic = staging_logic(domain)
    logic = re.sub(r"^\s*WITH\s", "", logic, count=1)
    return (f"-- reference integration: {fmt} / {domain}\nWITH acq_src AS (\n    select\n        {casts}\n    from (\n"
            f"{inner}\n    ) as inv\n)\n\n, {logic}\n")


def wide_reference_sql(product: str, extended: list) -> str:
    return products.sql(product, extended)


def has_reference(fmt: str, domain: str) -> bool:
    return fmt in ("d1", "d2", "d3") or (REFSQL / fmt / f"{domain}.sql").exists()
