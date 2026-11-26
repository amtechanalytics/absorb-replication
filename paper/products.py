"""Four wide data products on top of the OMOP tables (written for this study). Each has one row per person
(or person-year) and one column per category value. The column list is fixed in the SQL, as in a hand-kept
pivot: when acquired data brings category values the acquirer never had, the product must grow.

Definitions follow the usual covariate conventions for OMOP data: binary condition indicators per concept,
most recent measurement value per concept, visit counts per visit concept and period, and observation
(coverage) time per payer."""
from __future__ import annotations

import re

from . import spec

TOP_CONDITIONS = 40
TOP_LABS = 30


def slug(v) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(v).lower()).strip("_")


def col_name(product: str, cat) -> str:
    return {"dp_condition_flags": "cond_", "dp_latest_labs": "lab_", "dp_utilisation_yearly": "visits_",
            "dp_coverage_months": "months_"}[product] + slug(cat)


CATEGORY_SQL = {
    # (category value, persons, description) present in a world's OMOP tables, for one group or all
    "dp_condition_flags": """select co.condition_source_value as cat, count(distinct co.person_id) as n
        from {s}.condition_occurrence co join {s}.person p using (person_id) {w} group by 1""",
    "dp_latest_labs": """select m.measurement_source_value as cat, count(distinct m.person_id) as n
        from {s}.measurement m join {s}.person p using (person_id) {w} {a} m.value_as_number is not null group by 1""",
    "dp_utilisation_yearly": """select cast(v.visit_concept_id as varchar) as cat, count(distinct v.person_id) as n
        from {s}.visit_occurrence v join {s}.person p using (person_id) {w} group by 1""",
    "dp_coverage_months": """select pp.plan_source_value as cat, count(distinct pp.person_id) as n
        from {s}.payer_plan_period pp join {s}.person p using (person_id) {w} {a} pp.plan_source_value is not null group by 1""",
}


def categories(con, product: str, group: str | None, schema=spec.SCHEMA) -> dict:
    """{category: persons} among one group ('acquirer' / 'acquired') or everyone."""
    w = ""
    if group:
        w = f"where p.person_source_value in (select id from study.patients where grp='{group}')"
    q = CATEGORY_SQL[product].format(s=schema, w=w, a="and" if w else "where")
    return {r[0]: r[1] for r in con.execute(q).fetchall() if r[0] is not None}


def existing_list(product: str, acquirer_cats: dict) -> list:
    """The acquirer's column list: its most frequent categories (all of them for the two small products)."""
    ranked = sorted(acquirer_cats.items(), key=lambda kv: (-kv[1], str(kv[0])))
    if product == "dp_condition_flags":
        ranked = ranked[:TOP_CONDITIONS]
    elif product == "dp_latest_labs":
        ranked = ranked[:TOP_LABS]
    return sorted(str(k) for k, _ in ranked)


def new_list(acquirer_cats: dict, acquired_cats: dict) -> list:
    """Category values present in the acquired rows that the acquirer's data never had."""
    return sorted(str(k) for k in acquired_cats if k not in acquirer_cats)


def sql(product: str, cats: list) -> str:
    """The product's dbt model for a column list (existing columns first, new ones appended)."""
    r = "{{ ref('%s') }}"
    if product == "dp_condition_flags":
        cols = "\n".join(f"    , max(case when co.condition_source_value = '{c}' then 1 else 0 end) as {col_name(product, c)}"
                         for c in cats)
        return (f"select\n    p.person_id\n{cols}\nfrom {r % 'person'} as p\nleft join {r % 'condition_occurrence'} as co\n"
                f"    on co.person_id = p.person_id\ngroup by p.person_id\n")
    if product == "dp_latest_labs":
        cols = "\n".join(f"    , max(case when l.measurement_source_value = '{c}' then l.value_as_number end) as {col_name(product, c)}"
                         for c in cats)
        return (f"with ranked as (\n    select\n        m.person_id\n        , m.measurement_source_value\n        , m.value_as_number\n"
                f"        , row_number() over (\n            partition by m.person_id, m.measurement_source_value\n"
                f"            order by m.measurement_datetime desc, m.value_as_number desc\n        ) as rn\n"
                f"    from {r % 'measurement'} as m\n    where m.value_as_number is not null\n)\n\n"
                f"select\n    p.person_id\n{cols}\nfrom {r % 'person'} as p\nleft join ranked as l\n"
                f"    on l.person_id = p.person_id and l.rn = 1\ngroup by p.person_id\n")
    if product == "dp_utilisation_yearly":
        cols = "\n".join(f"    , count(case when v.visit_concept_id = {c} then 1 end) as {col_name(product, c)}" for c in cats)
        return (f"select\n    v.person_id\n    , extract(year from v.visit_start_date) as visit_year\n{cols}\n"
                f"from {r % 'visit_occurrence'} as v\ngroup by v.person_id, extract(year from v.visit_start_date)\n")
    if product == "dp_coverage_months":
        cols = "\n".join(
            f"    , coalesce(sum(case when pp.plan_source_value = '{c.replace(chr(39), chr(39) * 2)}' then "
            f"datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as {col_name(product, c)}"
            for c in cats)
        return (f"select\n    p.person_id\n{cols}\nfrom {r % 'person'} as p\nleft join {r % 'payer_plan_period'} as pp\n"
                f"    on pp.person_id = p.person_id\ngroup by p.person_id\n")
    raise ValueError(product)


def tests_yaml() -> str:
    lines = ["version: 2", "", "models:"]
    for p in spec.PRODUCTS:
        lines += [f"  - name: {p}", "    columns:", "      - name: person_id", "        tests:", "          - not_null"]
        if p != "dp_utilisation_yearly":
            lines += ["          - unique"]
        else:
            lines += ["      - name: visit_year", "        tests:", "          - not_null"]
    return "\n".join(lines) + "\n"


def key_columns(product: str) -> list:
    return ["person_id", "visit_year"] if product == "dp_utilisation_yearly" else ["person_id"]
