"""Scoring: natural projections of the scored tables, row alignment and cell counts.

A natural projection replaces every generated key by what it stands for (person -> source patient id, visit ->
its dates and concept, provider -> its source id) and drops the table's own surrogate key, so that two builds
can be compared although their row numbers differ. Values are compared as text; floating-point values are
rounded to four decimals."""
from __future__ import annotations

import collections
from pathlib import Path

from . import env, spec

S = spec.SCHEMA
FK = {  # column -> (lookup table, its id column, expression over alias l)
    "visit_occurrence_id": ("visit_occurrence", "visit_occurrence_id",
                            "concat_ws('|', l.visit_start_date, l.visit_end_date, l.visit_concept_id)"),
    "preceding_visit_occurrence_id": ("visit_occurrence", "visit_occurrence_id",
                                      "concat_ws('|', l.visit_start_date, l.visit_end_date, l.visit_concept_id)"),
    "visit_detail_id": ("visit_detail", "visit_detail_id",
                        "concat_ws('|', l.visit_detail_start_datetime, l.visit_detail_end_datetime, l.visit_detail_concept_id)"),
    "preceding_visit_detail_id": ("visit_detail", "visit_detail_id",
                                  "concat_ws('|', l.visit_detail_start_datetime, l.visit_detail_end_datetime, l.visit_detail_concept_id)"),
    "parent_visit_detail_id": ("visit_detail", "visit_detail_id",
                               "concat_ws('|', l.visit_detail_start_datetime, l.visit_detail_end_datetime, l.visit_detail_concept_id)"),
    "provider_id": ("provider", "provider_id", "l.provider_source_value"),
    "care_site_id": ("care_site", "care_site_id", "l.care_site_source_value"),
    "location_id": ("location", "location_id", "l.location_source_value"),
}


def table_columns(con, table: str, catalog: str | None = None) -> list:
    cat = f"and table_catalog='{catalog}'" if catalog else ""
    return con.execute(f"select column_name, data_type from information_schema.columns where table_schema='{S}' "
                       f"and table_name='{table}' {cat} order by ordinal_position").fetchall()


def projection_sql(con, table: str, catalog: str) -> tuple[str, list]:
    """SELECT giving (grp, natural columns as text...) and the list of output column names."""
    cols = table_columns(con, table, catalog)
    if not cols:
        raise RuntimeError(f"table {table} not found")
    pk = spec.PRIMARY_KEY.get(table)
    q = f"{catalog}.{S}"
    sel, joins, names = [], [], []
    n = 0
    for c, ty in cols:
        if c == pk:
            continue
        names.append(c)
        if c == "person_id":
            sel.append("pp.person_source_value as person_id")
        elif c in FK:
            lt, lid, expr = FK[c]
            n += 1
            a = f"l{n}"
            joins.append(f"left join {q}.{lt} as {a} on {a}.{lid} = t.{c}")
            sel.append(f"{expr.replace('l.', a + '.')} as {c}")
        elif ty in ("FLOAT", "DOUBLE", "REAL") or ty.startswith("DECIMAL"):
            sel.append(f"cast(round(cast(t.{c} as double), 4) as varchar) as {c}")
        else:
            sel.append(f"cast(t.{c} as varchar) as {c}")
    sql = (f"select sp.grp as grp, {', '.join(sel)} from {q}.{table} as t "
           f"join {q}.person as pp on pp.person_id = t.person_id "
           f"join {catalog}.study.patients as sp on sp.id = pp.person_source_value " + " ".join(joins))
    return sql, names


def export_projection(world_db: Path, out_db: Path, tables=None) -> dict:
    """Write the natural projection of every scored table of a world into a small database, plus one row per
    table with the count and an order-independent hash of the acquirer's rows with generated keys kept."""
    out_db.unlink(missing_ok=True)
    con = env.connect(out_db)
    con.execute(f"attach '{world_db}' as w (read_only)")
    con.execute("create table keyhash(tbl varchar, n bigint, h varchar)")
    info = {}
    for t in tables or list(spec.SCORED):
        if not table_columns(con, t, "w"):
            info[t] = {"missing": True}
            continue
        sql, names = projection_sql(con, t, "w")
        con.execute(f'create table "{t}" as {sql}')
        n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        raw = [c for c, _ in table_columns(con, t, "w")]
        h = con.execute(
            f"select count(*), cast(coalesce(sum(cast(hash({', '.join('t.' + c for c in raw)}) as hugeint)), 0) as varchar) "
            f"from w.{S}.{t} t join w.{S}.person pp on pp.person_id = t.person_id "
            f"join w.study.patients sp on sp.id = pp.person_source_value where sp.grp = 'acquirer'").fetchone()
        con.execute("insert into keyhash values (?, ?, ?)", [t, h[0], h[1]])
        info[t] = {"rows": n, "columns": names}
    con.execute("detach w")
    con.close()
    return info


def proj_columns(con, catalog: str, table: str) -> list:
    return [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_catalog='{catalog}' "
                                      f"and table_name='{table}' and table_schema='main' order by ordinal_position").fetchall()
            if r[0] != "grp"]


def has_table(con, catalog: str, table: str) -> bool:
    return bool(con.execute(f"select 1 from information_schema.tables where table_catalog='{catalog}' and "
                            f"table_name='{table}' and table_schema='main'").fetchall())


def contributed(con, world: str, minus: str, table: str, cols: list, grp: str = "acquired") -> list:
    """Rows of `world` (group grp) that are not in `minus` (multiset difference), over the given columns."""
    if not has_table(con, world, table):
        return []
    have = set(proj_columns(con, world, table))
    c = ", ".join(f'"{x}"' if x in have else f'cast(null as varchar) as "{x}"' for x in cols)
    q = f"select {c} from {world}.\"{table}\" where grp = '{grp}'"
    if minus and has_table(con, minus, table):
        mh = set(proj_columns(con, minus, table))
        c2 = ", ".join(f'"{x}"' if x in mh else f'cast(null as varchar) as "{x}"' for x in cols)
        q += f" except all select {c2} from {minus}.\"{table}\" where grp = '{grp}'"
    return con.execute(f"select * from ({q}) order by all").fetchall()


def relaxed_key(key: list) -> list:
    return key[:-1] if len(key) > 1 else key


def align(gold: list, cand: list, cols: list, key: list) -> tuple[list, int]:
    """Pair candidate rows with gold rows: identical rows first, then rows with the same natural key, then rows
    with the same key without its date. Returns, per gold row, a bit mask of the cells the paired candidate
    row gets right (0 when unpaired), and the number of candidate rows left unpaired."""
    ncol = len(cols)
    full = (1 << ncol) - 1
    masks = [0] * len(gold)
    pool = collections.defaultdict(list)
    for j, r in enumerate(cand):
        pool[r].append(j)
    used = [False] * len(cand)
    open_gold = []
    for i, r in enumerate(gold):
        lst = pool.get(r)
        if lst:
            used[lst.pop()] = True
            masks[i] = full
        else:
            open_gold.append(i)
    for k in (key, relaxed_key(key)):
        if not open_gold:
            break
        kidx = [cols.index(c) for c in k]
        buckets = collections.defaultdict(list)
        for j, r in enumerate(cand):
            if not used[j]:
                buckets[tuple(r[x] for x in kidx)].append(j)
        still = []
        by_key = collections.defaultdict(list)
        for i in open_gold:
            by_key[tuple(gold[i][x] for x in kidx)].append(i)
        for kv, gi in by_key.items():
            cj = buckets.get(kv, [])
            if not cj:
                still.extend(gi)
                continue
            if len(gi) * len(cj) <= 900:
                pairs = []
                for i in gi:
                    for j in cj:
                        pairs.append((sum(1 for a, b in zip(gold[i], cand[j]) if a == b), i, j))
                pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
                gdone, cdone = set(), set()
                for _s, i, j in pairs:
                    if i in gdone or j in cdone:
                        continue
                    gdone.add(i)
                    cdone.add(j)
                    used[j] = True
                    masks[i] = _mask(gold[i], cand[j])
                still.extend(i for i in gi if i not in gdone)
            else:
                gi_s = sorted(gi, key=lambda i: tuple("" if v is None else v for v in gold[i]))
                cj_s = sorted(cj, key=lambda j: tuple("" if v is None else v for v in cand[j]))
                for i, j in zip(gi_s, cj_s):
                    used[j] = True
                    masks[i] = _mask(gold[i], cand[j])
                still.extend(gi_s[len(cj_s):])
        open_gold = still
    return masks, used.count(False)


def _mask(g, c) -> int:
    m = 0
    for x, (a, b) in enumerate(zip(g, c)):
        if a == b:
            m |= 1 << x
    return m


def popcount(x: int) -> int:
    return bin(x).count("1")


def column_mask(cols: list, exclude: set) -> int:
    m = 0
    for x, c in enumerate(cols):
        if c not in exclude:
            m |= 1 << x
    return m


def multiset_diff(con, a: str, b: str, table: str, grp: str) -> int:
    """Number of rows of group grp that differ between two projections (either direction)."""
    if not has_table(con, a, table) or not has_table(con, b, table):
        return -1
    ca, cb = proj_columns(con, a, table), proj_columns(con, b, table)
    common = [x for x in ca if x in cb]      # a wide product may have gained columns: compare the shared ones
    if not common:
        return -2
    c = ", ".join(f'"{x}"' for x in common)
    q1 = f"select {c} from {a}.\"{table}\" where grp='{grp}' except all select {c} from {b}.\"{table}\" where grp='{grp}'"
    q2 = f"select {c} from {b}.\"{table}\" where grp='{grp}' except all select {c} from {a}.\"{table}\" where grp='{grp}'"
    return con.execute(f"select (select count(*) from ({q1})) + (select count(*) from ({q2}))").fetchone()[0]


def keyhashes(con, catalog: str) -> dict:
    return {r[0]: (r[1], r[2]) for r in con.execute(f"select tbl, n, h from {catalog}.keyhash").fetchall()}
