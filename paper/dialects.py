"""Three controlled CSV dialects of the acquired data, each a deterministic transformation of the Synthea CSV:
d1 renames tables and columns; d2 changes structure (splits, merges, date formats); d3 changes units and code
lists. forward() lands a dialect; inverse_sql() is the authors' mapping back to the source shape, used by the
reference solutions."""
from __future__ import annotations

from . import spec

# ---------------------------------------------------------------- d1: renames
D1_TABLE = {"patients": "member_master", "encounters": "visit_log", "conditions": "dx_history",
            "procedures": "px_history", "medications": "rx_orders", "observations": "result_feed",
            "immunizations": "vaccinations", "allergies": "allergy_list"}
D1_COL = {"Id": "rec_uuid", "START": "begin_ts", "STOP": "end_ts", "DATE": "event_ts", "PATIENT": "member_ref",
          "ENCOUNTER": "visit_ref", "CODE": "concept_cd", "DESCRIPTION": "concept_label", "SYSTEM": "code_scheme",
          "REASONCODE": "why_cd", "REASONDESCRIPTION": "why_label", "BASE_COST": "unit_charge", "PAYER": "plan_ref",
          "PAYER_COVERAGE": "plan_paid", "ORGANIZATION": "facility_ref", "PROVIDER": "clinician_ref",
          "ENCOUNTERCLASS": "care_setting", "BASE_ENCOUNTER_COST": "visit_charge", "TOTAL_CLAIM_COST": "billed_total",
          "VALUE": "result_val", "UNITS": "result_uom", "TYPE": "kind", "CATEGORY": "grouping", "DISPENSES": "fills",
          "TOTALCOST": "charge_total", "BIRTHDATE": "dob", "DEATHDATE": "dod", "SSN": "national_id",
          "DRIVERS": "licence_no", "PASSPORT": "passport_no", "PREFIX": "title", "FIRST": "given_nm",
          "LAST": "family_nm", "SUFFIX": "name_suffix", "MAIDEN": "birth_family_nm", "MARITAL": "marital_cd",
          "RACE": "race_txt", "ETHNICITY": "ethnic_txt", "GENDER": "sex_cd", "BIRTHPLACE": "born_in",
          "ADDRESS": "street", "CITY": "town", "STATE": "region", "COUNTY": "district", "ZIP": "postcode",
          "LAT": "geo_lat", "LON": "geo_lon", "HEALTHCARE_EXPENSES": "lifetime_spend",
          "HEALTHCARE_COVERAGE": "lifetime_covered", "REACTION1": "rx1_cd", "DESCRIPTION1": "rx1_label",
          "SEVERITY1": "rx1_sev", "REACTION2": "rx2_cd", "DESCRIPTION2": "rx2_label", "SEVERITY2": "rx2_sev"}

# ---------------------------------------------------------------- d2: structure
D2_MERGE = {"*": [("CODE", "DESCRIPTION", "code_display"), ("REASONCODE", "REASONDESCRIPTION", "reason")]}
D2_ENC_CHARGES = ["BASE_ENCOUNTER_COST", "TOTAL_CLAIM_COST", "PAYER_COVERAGE"]

# ---------------------------------------------------------------- d3: units and code lists
D3_UNITS = {"kg": ("g", 1000), "cm": ("m", 0.01), "mg/dL": ("mg/L", 10)}
D3_PREFIX = {"encounters": {"CODE": "SCT:", "REASONCODE": "SCT:"}, "conditions": {"CODE": "SCT:"},
             "procedures": {"CODE": "SCT:", "REASONCODE": "SCT:"}, "medications": {"CODE": "RXN:", "REASONCODE": "SCT:"},
             "observations": {"CODE": "LN:"}, "immunizations": {"CODE": "CVX:"}, "allergies": {"CODE": "ALG:"}}
D3_LISTS = {
    "gender": {"M": "male", "F": "female"},
    "marital": {"M": "1", "S": "2", "D": "3", "W": "4"},
    "race": {"white": "R1", "black": "R2", "asian": "R3", "native": "R4", "hawaiian": "R5", "other": "R9"},
    "ethnicity": {"hispanic": "H", "nonhispanic": "N"},
    "encounter_class": {"ambulatory": "E01", "wellness": "E02", "outpatient": "E03", "urgentcare": "E04",
                        "emergency": "E05", "inpatient": "E06", "snf": "E07", "hospice": "E08", "home": "E09",
                        "virtual": "E10"},
}
D3_LISTED = {"patients": {"GENDER": "gender", "MARITAL": "marital", "RACE": "race", "ETHNICITY": "ethnicity"},
             "encounters": {"ENCOUNTERCLASS": "encounter_class"}}


def columns(con, table: str):
    return con.execute(f"select column_name, data_type from information_schema.columns where "
                       f"table_schema='{spec.SRC_SCHEMA}' and table_name='{table}' order by ordinal_position").fetchall()


def _q(c):
    return '"' + c + '"'


def _acq(table):
    col = spec.PATIENT_COLUMN.get(table, "PATIENT")
    return f'from {spec.SRC_SCHEMA}."{table}" where "{col}" in (select id from study.patients where grp=\'acquired\')'


# ================================================================ forward
def land(con, fmt: str, schema: str) -> None:
    for d in spec.DOMAINS:
        cols = columns(con, d)
        if fmt == "d1":
            sel = ", ".join(f"{_q(c)} as {D1_COL[c]}" for c, _ in cols)
            con.execute(f"create table {schema}.{D1_TABLE[d]} as select {sel} {_acq(d)} order by all")
        elif fmt == "d2":
            _land_d2(con, schema, d, cols)
        elif fmt == "d3":
            _land_d3(con, schema, d, cols)
        else:
            raise ValueError(fmt)
    if fmt == "d3":
        con.execute(f"create table {schema}.code_map(list_name varchar, local_code varchar, standard_value varchar)")
        con.executemany(f"insert into {schema}.code_map values (?, ?, ?)",
                        [(ln, loc, std) for ln, m in sorted(D3_LISTS.items()) for std, loc in sorted(m.items())])


def _d2_exprs(d, cols, skip=()):
    names = [c for c, _ in cols]
    merged = {}
    for a, b, new in D2_MERGE["*"]:
        if a in names and b in names:
            merged[a] = (b, new)
    out = []
    drop = {b for b, _ in merged.values()}
    for c, ty in cols:
        if c in skip or c in drop:
            continue
        if d == "patients" and c in ("LAST", "STATE", "ZIP"):
            continue
        if d == "patients" and c == "FIRST":
            out.append('"LAST" || \', \' || "FIRST" as full_name')
        elif d == "patients" and c == "CITY":
            out.append('"CITY" || \', \' || "STATE" || coalesce(\' \' || "ZIP", \'\') as city_state_zip')
        elif c in merged:
            b, new = merged[c]
            out.append(f"case when {_q(c)} is null then null else {_q(c)} || ' | ' || coalesce({_q(b)}, '') end as {new}")
        elif ty.startswith("TIMESTAMP"):
            out.append(f"strftime({_q(c)} at time zone 'UTC', '%m/%d/%Y') as {c.lower()}_date")
            out.append(f"strftime({_q(c)} at time zone 'UTC', '%H:%M:%S') as {c.lower()}_time")
        elif ty == "DATE":
            out.append(f"strftime({_q(c)}, '%d-%b-%Y') as {c.lower()}")
        else:
            out.append(f"{_q(c)} as {_q(c.lower())}")
    return out


def _land_d2(con, schema, d, cols):
    if d == "encounters":
        con.execute(f"create table {schema}.encounters as select {', '.join(_d2_exprs(d, cols, skip=D2_ENC_CHARGES))} "
                    f"{_acq(d)} order by all")
        con.execute(f'create table {schema}.encounter_charges as select "Id" as encounter_id, '
                    + ", ".join(f"{_q(c)} as {c.lower()}" for c in D2_ENC_CHARGES) + f" {_acq(d)} order by all")
    else:
        con.execute(f"create table {schema}.{d} as select {', '.join(_d2_exprs(d, cols))} {_acq(d)} order by all")


def _land_d3(con, schema, d, cols):
    out = []
    for c, _ty in cols:
        pre = D3_PREFIX.get(d, {}).get(c)
        lst = D3_LISTED.get(d, {}).get(c)
        if pre:
            out.append(f"'{pre}' || {_q(c)} as {_q(c)}")
        elif lst:
            cases = " ".join(f"when '{std}' then '{loc}'" for std, loc in sorted(D3_LISTS[lst].items()))
            out.append(f"case {_q(c)} {cases} else {_q(c)} end as {_q(c)}")
        elif d == "observations" and c == "VALUE":
            cases = " ".join(
                f"when \"TYPE\"='numeric' and \"UNITS\"='{u}' then cast(cast(cast(\"VALUE\" as decimal(28,10)) * "
                f"cast({k} as decimal(12,4)) as double) as varchar)" for u, (_n, k) in sorted(D3_UNITS.items()))
            out.append(f'case {cases} else "VALUE" end as "VALUE"')
        elif d == "observations" and c == "UNITS":
            cases = " ".join(f"when \"TYPE\"='numeric' and \"UNITS\"='{u}' then '{n}'" for u, (n, _k) in sorted(D3_UNITS.items()))
            out.append(f'case {cases} else "UNITS" end as "UNITS"')
        else:
            out.append(f"{_q(c)} as {_q(c)}")
    con.execute(f"create table {schema}.{d} as select {', '.join(out)} {_acq(d)} order by all")


# ================================================================ inverse (source-shaped select)
def inverse_sql(con, fmt: str, d: str) -> str:
    """SELECT that turns the dialect's tables back into the columns of the pipeline's source table for d."""
    cols = columns(con, d)
    schema = f"raw_{fmt}"
    if fmt == "d1":
        return ("select " + ", ".join(f"{D1_COL[c]} as {_q(c)}" for c, _ in cols)
                + f" from {{{{ source('{schema}', '{D1_TABLE[d]}') }}}}")
    if fmt == "d2":
        names = [c for c, _ in cols]
        merged = {}
        for a, b, new in D2_MERGE["*"]:
            if a in names and b in names:
                merged[a] = new
                merged[b] = new
        out = []
        for c, ty in cols:
            if d == "patients" and c == "FIRST":
                e = "split_part(full_name, ', ', 2)"
            elif d == "patients" and c == "LAST":
                e = "split_part(full_name, ', ', 1)"
            elif d == "patients" and c == "CITY":
                e = "split_part(city_state_zip, ', ', 1)"
            elif d == "patients" and c == "STATE":
                e = "regexp_replace(split_part(city_state_zip, ', ', 2), ' [0-9]{5}$', '')"
            elif d == "patients" and c == "ZIP":
                e = "nullif(regexp_extract(city_state_zip, ' ([0-9]{5})$', 1), '')"
            elif c in merged and c in ("CODE", "REASONCODE"):
                e = f"split_part({merged[c]}, ' | ', 1)"
            elif c in merged:
                e = (f"nullif(substr({merged[c]}, length(split_part({merged[c]}, ' | ', 1)) + 4), '')")
            elif ty.startswith("TIMESTAMP"):
                e = (f"cast(strptime({c.lower()}_date || ' ' || {c.lower()}_time, '%m/%d/%Y %H:%M:%S') as timestamp) "
                     f"at time zone 'UTC'")
            elif ty == "DATE":
                e = f"cast(strptime({_q(c.lower())}, '%d-%b-%Y') as date)"
            elif d == "encounters" and c in D2_ENC_CHARGES:
                e = f"ch.{c.lower()}"
            else:
                e = ("e." if d == "encounters" else "") + _q(c.lower())
            out.append(f"{e} as {_q(c)}")
        if d == "encounters":
            return ("select " + ", ".join(out) + f" from {{{{ source('{schema}', 'encounters') }}}} e left join "
                    f"{{{{ source('{schema}', 'encounter_charges') }}}} ch on ch.encounter_id = e.\"id\"")
        return "select " + ", ".join(out) + f" from {{{{ source('{schema}', '{d}') }}}}"
    if fmt == "d3":
        out = []
        joins = []
        for c, _ty in cols:
            pre = D3_PREFIX.get(d, {}).get(c)
            lst = D3_LISTED.get(d, {}).get(c)
            if pre:
                e = f"substr(t.{_q(c)}, {len(pre) + 1})"
            elif lst:
                a = f"m_{lst}"
                joins.append(f"left join {{{{ source('{schema}', 'code_map') }}}} {a} on {a}.list_name = '{lst}' "
                             f"and {a}.local_code = t.{_q(c)}")
                e = f"coalesce({a}.standard_value, t.{_q(c)})"
            elif d == "observations" and c == "VALUE":
                cases = " ".join(
                    f"when t.\"TYPE\"='numeric' and t.\"UNITS\"='{n}' then cast(cast(cast(t.\"VALUE\" as decimal(28,10)) / "
                    f"cast({k} as decimal(12,4)) as double) as varchar)" for _u, (n, k) in sorted(D3_UNITS.items()))
                e = f'case {cases} else t."VALUE" end'
            elif d == "observations" and c == "UNITS":
                cases = " ".join(f"when t.\"TYPE\"='numeric' and t.\"UNITS\"='{n}' then '{u}'"
                                 for u, (n, _k) in sorted(D3_UNITS.items()))
                e = f'case {cases} else t."UNITS" end'
            else:
                e = f"t.{_q(c)}"
            out.append(f"{e} as {_q(c)}")
        return ("select " + ", ".join(out) + f" from {{{{ source('{schema}', '{d}') }}}} t " + " ".join(joins))
    raise ValueError(fmt)


def source_tables(fmt: str, d: str) -> list[str]:
    if fmt == "d1":
        return [D1_TABLE[d]]
    if fmt == "d2":
        return ["encounters", "encounter_charges"] if d == "encounters" else [d]
    if fmt == "d3":
        return [d] + (["code_map"] if d in D3_LISTED else [])
    raise ValueError(fmt)
