"""Population: one Synthea run, the acquirer/acquired split, and the landing of the acquired data in each
source format (FHIR R4, FHIR STU3, claims, three CSV dialects)."""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import shutil
from pathlib import Path

from . import dialects, env, spec

SYN = env.WORK / "synthea"
OUT = SYN / "out"
SRC = env.WORK / "sources"
LAND = env.WORK / "landing"
SPLIT = env.WORK / "split.json"

FHIR_TYPES = ["Patient", "Encounter", "Condition", "Procedure", "MedicationRequest", "Medication",
              "MedicationAdministration", "Observation", "Immunization", "AllergyIntolerance", "Claim"]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- 1. Synthea
def generate(hb=None) -> dict:
    marker = SYN / "generated.json"
    if marker.exists():
        return json.loads(marker.read_text())
    if SYN.exists():
        shutil.rmtree(SYN)
    SYN.mkdir(parents=True)
    jar = env.asset("synthea_jar")
    cmd = [env.java(), "-Xmx6g", "-jar", jar, "-s", spec.SEED, "-cs", spec.SEED, "-r", spec.REFERENCE_DATE,
           "-p", spec.N_REQUEST, "--exporter.csv.export=true", "--exporter.fhir.export=true",
           "--exporter.fhir_stu3.export=true", "--exporter.cpcds.export=true",
           "--exporter.hospital.fhir.export=false", "--exporter.practitioner.fhir.export=false",
           "--exporter.hospital.fhir_stu3.export=false", "--exporter.practitioner.fhir_stu3.export=false",
           "--generate.thread_pool_size=1",      # one generator thread: with several, the population depends on timing
           "--exporter.baseDirectory=./out", spec.STATE]
    genv = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(env.WORK / "home"), "LANG": "C.UTF-8", "TZ": "UTC"}
    (env.WORK / "home").mkdir(parents=True, exist_ok=True)
    code, out = env.run_cmd(cmd, cwd=SYN, env=genv, timeout=3 * 3600, hb=hb, log=SYN / "synthea.log")
    if code != 0 or not (OUT / "csv" / "patients.csv").exists():
        raise RuntimeError(f"Synthea failed (exit {code}): {out[-1500:]}")
    n = sum(1 for _ in open(OUT / "csv" / "patients.csv")) - 1
    info = {"patients_generated": n, "jar_sha256": _sha(Path(jar)), "seed": spec.SEED,
            "reference_date": spec.REFERENCE_DATE, "requested": spec.N_REQUEST,
            "fhir_r4_files": len(glob.glob(str(OUT / "fhir" / "*.json"))),
            "fhir_stu3_files": len(glob.glob(str(OUT / "fhir_stu3" / "*.json")))}
    marker.write_text(json.dumps(info, indent=1))
    return info


# ---------------------------------------------------------------- 2. split
def _order(pid: str) -> str:
    return hashlib.sha1(f"{spec.SEED}|{pid}".encode()).hexdigest()


def split() -> dict:
    """Acquired group: carriers of a fixed set of condition and laboratory codes (chosen by a rule from the
    data: rarest mapped codes first, carriers capped), filled up in hash order. Acquirer: next in hash order."""
    if SPLIT.exists():
        return json.loads(SPLIT.read_text())
    con = env.connect(":memory:")
    c = OUT / "csv"
    repo = env.asset("dbt_synthea")
    con.execute(f"create table concept as select * from read_csv('{repo}/seeds/vocabulary/concept_seed.csv', "
                f"all_varchar=true, header=true)")
    for t in ("patients", "conditions", "observations"):
        con.execute(f"create table {t} as select * from read_csv('{c}/{t}.csv', all_varchar=true, header=true, quote='')")
    pats = sorted((r[0] for r in con.execute('select "Id" from patients').fetchall()), key=_order)
    if len(pats) < spec.N_ACQUIRER + spec.N_ACQUIRED:
        raise RuntimeError(f"only {len(pats)} patients generated; {spec.N_ACQUIRER + spec.N_ACQUIRED} needed")
    cap = int(spec.N_ACQUIRED * spec.ONLY_CARRIER_CAP)
    cond = con.execute("""
        select c."CODE", count(distinct c."PATIENT") n, list(distinct c."PATIENT") from conditions c
        where c."CODE" in (select concept_code from concept where vocabulary_id='SNOMED' and domain_id='Condition'
                           and standard_concept='S' and invalid_reason is null)
        group by 1 having count(distinct c."PATIENT") >= 2 order by n, 1""").fetchall()
    labs = con.execute("""
        select o."CODE", count(distinct o."PATIENT") n, list(distinct o."PATIENT") from observations o
        where o."TYPE"='numeric' and try_cast(o."VALUE" as double) is not null
          and o."CODE" in (select concept_code from concept where vocabulary_id='LOINC' and domain_id='Measurement'
                           and standard_concept='S' and invalid_reason is null)
        group by 1 having count(distinct o."PATIENT") >= 2 order by n, 1""").fetchall()
    carriers: set = set()
    only = {"conditions": [], "labs": []}
    for kind, rows, want in (("conditions", cond, spec.N_ONLY_CONDITIONS), ("labs", labs, spec.N_ONLY_LABS)):
        for code, _n, plist in rows:
            if len(only[kind]) >= want:
                break
            u = carriers | set(plist)
            if len(u) <= cap:
                carriers = u
                only[kind].append(code)
    if not only["conditions"] or not only["labs"]:
        raise RuntimeError(f"split rule found no acquired-only codes: {only}")
    acquired = sorted(carriers, key=_order)
    rest = [p for p in pats if p not in carriers]
    acquired += rest[: spec.N_ACQUIRED - len(acquired)]
    rest = rest[spec.N_ACQUIRED - len(carriers):]
    acquirer = rest[: spec.N_ACQUIRER]
    out = {"acquirer": sorted(acquirer), "acquired": sorted(acquired), "unused": len(pats) - len(acquirer) - len(acquired),
           "only_codes": only, "carriers": len(carriers), "generated": len(pats)}
    assert len(out["acquirer"]) == spec.N_ACQUIRER and len(out["acquired"]) == spec.N_ACQUIRED
    assert not set(out["acquirer"]) & set(out["acquired"])
    SPLIT.write_text(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------- 3. source CSVs (acquirer + acquired, sorted)
def write_sources() -> dict:
    """work/sources/<table>.csv for the used patients, rows sorted, plus sha256 of every file."""
    marker = SRC / "sources.json"
    if marker.exists():
        return json.loads(marker.read_text())
    sp = split()
    used = set(sp["acquirer"]) | set(sp["acquired"])
    SRC.mkdir(parents=True, exist_ok=True)
    info = {}
    for t in spec.SOURCE_TABLES:
        src = OUT / "csv" / f"{t}.csv"
        with open(src, newline="") as f:
            lines = f.read().split("\n")
        header, body = lines[0].rstrip("\r"), [ln.rstrip("\r") for ln in lines[1:] if ln.strip()]
        cols = header.split(",")
        if t not in spec.SHARED_TABLES:
            i = cols.index(spec.PATIENT_COLUMN.get(t, "PATIENT"))
            keep = []
            for ln in body:
                parts = ln.split(",")
                if len(parts) != len(cols):
                    raise RuntimeError(f"{t}: a row has {len(parts)} fields, header has {len(cols)}")
                if parts[i] in used:
                    keep.append(ln)
            body = keep
        body.sort()
        dst = SRC / f"{t}.csv"
        dst.write_text(header + "\n" + "\n".join(body) + ("\n" if body else ""))
        info[t] = {"rows": len(body), "sha256": _sha(dst)}
    marker.write_text(json.dumps(info, indent=1))
    return info


def load_sources(con) -> None:
    """Replace the pipeline's source tables with the study population (column types as the pipeline declares
    them) and record the group of every patient in study.patients."""
    sp = split()
    info = write_sources()
    con.execute("create schema if not exists study")
    con.execute("create or replace table study.patients(id varchar, grp varchar)")
    con.executemany("insert into study.patients values (?, ?)",
                    [(p, "acquirer") for p in sp["acquirer"]] + [(p, "acquired") for p in sp["acquired"]])
    for t in spec.SOURCE_TABLES:
        cols = con.execute(f"select column_name, data_type from information_schema.columns "
                           f"where table_schema='{spec.SRC_SCHEMA}' and table_name='{t}' order by ordinal_position").fetchall()
        if not cols:
            raise RuntimeError(f"source table {t} not found in {spec.SRC_SCHEMA}")
        path = SRC / f"{t}.csv"
        if info[t]["rows"] == 0:
            con.execute(f'delete from {spec.SRC_SCHEMA}."{t}"')
            continue
        sel = ", ".join(f'cast("{c}" as {ty}) as "{c}"' for c, ty in cols)
        con.execute(f'create or replace table {spec.SRC_SCHEMA}."{t}" as select {sel} from '
                    f"read_csv('{path}', all_varchar=true, header=true, quote='')")


def restrict_sources(con, group: str, domains=None) -> None:
    """Keep only one group's rows in the patient-level source tables (all of them, or the listed domains)."""
    tables = domains if domains is not None else [t for t in spec.SOURCE_TABLES if t not in spec.SHARED_TABLES]
    for t in tables:
        col = spec.PATIENT_COLUMN.get(t, "PATIENT")
        con.execute(f'delete from {spec.SRC_SCHEMA}."{t}" where "{col}" not in '
                    f"(select id from study.patients where grp='{group}')")


# ---------------------------------------------------------------- 4. landing of the acquired data
def _fhir_ndjson(version: str) -> Path:
    """One newline-delimited file per resource type with the acquired patients' resources."""
    out = LAND / version
    marker = out / "done.json"
    if marker.exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    acquired = set(split()["acquired"])
    folder = OUT / ("fhir" if version == "fhir_r4" else "fhir_stu3")
    files = {t: open(out / f"{t.lower()}.ndjson", "w") for t in FHIR_TYPES}
    counts = dict.fromkeys(FHIR_TYPES, 0)
    seen = 0
    for path in sorted(glob.glob(str(folder / "*.json"))):
        pid = Path(path).stem.rsplit("_", 1)[-1]
        if pid not in acquired:
            continue
        seen += 1
        with open(path) as f:
            bundle = json.load(f)
        for e in bundle.get("entry", []):
            r = e["resource"]
            t = r.get("resourceType")
            if t in files:
                if t == "Patient":
                    r.get("text", {}).pop("div", None)
                files[t].write(json.dumps({"id": r.get("id"), "resource": r}, separators=(",", ":")) + "\n")
                counts[t] += 1
    for f in files.values():
        f.close()
    if seen != len(acquired):
        raise RuntimeError(f"{version}: bundles found for {seen} of {len(acquired)} acquired patients")
    marker.write_text(json.dumps(counts))
    return out


def land(con, fmt: str) -> dict:
    """Create schema raw_<fmt> with the acquired organisation's data in that format."""
    schema = f"raw_{fmt}"
    con.execute(f"drop schema if exists {schema} cascade")
    con.execute(f"create schema {schema}")
    acq = "(select id from study.patients where grp='acquired')"
    if fmt in ("fhir_r4", "fhir_stu3"):
        d = _fhir_ndjson(fmt)
        counts = json.loads((d / "done.json").read_text())
        for t in FHIR_TYPES:
            if counts[t] == 0:
                con.execute(f"create table {schema}.{t.lower()}(id varchar, resource json)")
                continue
            con.execute(f"create table {schema}.{t.lower()} as select id, resource from read_json('{d}/{t.lower()}.ndjson', "
                        f"format='newline_delimited', columns={{'id': 'VARCHAR', 'resource': 'JSON'}}, "
                        f"maximum_object_size=67108864) order by id")
        # reference data both organisations share
        for t in ("providers", "organizations", "payers"):
            con.execute(f'create table {schema}.{t} as select * from {spec.SRC_SCHEMA}."{t}"')
    elif fmt == "claims":
        c = OUT / "cpcds"
        con.execute(f"""create table {schema}.claims as select * from read_csv('{c}/CPCDS_Claims.csv', all_varchar=true,
                    header=true) where "Patient account number" in {acq} order by all""")
        con.execute(f"""create table {schema}.members as select * from read_csv('{c}/CPCDS_Members.csv', all_varchar=true,
                    header=true) where "Member id" in {acq} order by all""")
        con.execute(f"""create table {schema}.coverages as select * from read_csv('{c}/CPCDS_Coverages.csv', all_varchar=true,
                    header=true) where "Member id" in {acq} order by all""")
    else:
        dialects.land(con, fmt, schema)
    tabs = con.execute(f"select table_name from information_schema.tables where table_schema='{schema}' order by 1").fetchall()
    return {t[0]: con.execute(f'select count(*) from {schema}."{t[0]}"').fetchone()[0] for t in tabs}


def sorted_export_hashes() -> dict:
    """sha256 of the sorted CSV exports of the whole run (reproducibility record)."""
    out = {}
    for path in sorted(glob.glob(str(OUT / "csv" / "*.csv"))):
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
        body = sorted(",".join(r) for r in rows[1:])
        out[Path(path).name] = {"rows": len(body),
                                "sha256_sorted": hashlib.sha256(("\n".join(body)).encode()).hexdigest()}
    return out
