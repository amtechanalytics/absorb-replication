"""Fixed mapping hint sheets (arm A3) and the category inventory shown in wide-product tasks."""
from __future__ import annotations

from . import dialects, products, spec

FORMAT_NAME = {"fhir_r4": "HL7 FHIR R4 resources (one JSON resource per row)",
               "fhir_stu3": "HL7 FHIR STU3 resources (one JSON resource per row)",
               "claims": "claims export (CARIN consumer-directed payer data, one row per claim line)",
               "d1": "CSV extract of another system (dialect 1)", "d2": "CSV extract of another system (dialect 2)",
               "d3": "CSV extract of another system (dialect 3)"}
FAMILY_NAME = {"fhir": "HL7 FHIR R4 resources", "claims": "a claims export (claim lines)",
               "dialect": "CSV extracts of another system with local code lists"}
NAMING = {
    "dp_condition_flags": "cond_<code>, where <code> is the condition's standard SNOMED CT code as stored in "
                          "condition_occurrence.condition_source_value (digits only).",
    "dp_latest_labs": "lab_<code>, where <code> is the LOINC code as stored in measurement.measurement_source_value, in "
                      "lower case with every run of characters other than letters and digits replaced by one underscore "
                      "(8302-2 becomes lab_8302_2).",
    "dp_utilisation_yearly": "visits_<visit_concept_id> (the OMOP visit concept id).",
    "dp_coverage_months": "months_<plan>, where <plan> is payer_plan_period.plan_source_value in lower case with every run "
                          "of characters other than letters and digits replaced by one underscore.",
}

_FHIR = {
    "patients": """- patient_id is the resource id. birth_date is birthDate. death_date is the first 10 characters of deceasedDateTime (the local date).
- ssn, drivers licence and passport are identifier[] entries whose type.coding[0].code is SS, DL and PPN.
- Names come from the name[] entry with use = official (prefix[0], given[0], family, suffix[0]); the maiden name is the family of the entry with use = maiden.
- marital status is maritalStatus.coding[0].code. gender: male becomes M, female becomes F.
- race is the ombCategory display of the us-core-race extension, written as the acquirer writes it: White = white, Black or African American = black, Asian = asian, American Indian or Alaska Native = native, Native Hawaiian or Other Pacific Islander = hawaiian, anything else = other. ethnicity: Hispanic or Latino = hispanic, otherwise nonhispanic.
- birthplace is city, state and country of the birthPlace extension joined by two spaces.
- address is address[0].line[0]; city and postalCode as given; the state is an abbreviation and the acquirer stores the full name (stg_map__states); latitude and longitude are in the geolocation extension of address[0].
- The county and the two healthcare amounts are not in the resource: return NULL.""",
    "encounters": """- encounter_id is the resource id; the patient is subject.reference without the urn:uuid: prefix; start and stop are period.start and period.end (they carry a UTC offset; the contract wants UTC).
- organization is the identifier after the | in serviceProvider.reference. The provider is not given by id: participant[0].individual.display is 'Dr. ' plus the provider's NAME in the shared providers table (match on name and organization).
- encounter class: class.code EMER = emergency, IMP = inpatient; for AMB look at type[0].coding[0].code: 702927004 = urgentcare, 162673000 / 410620009 / 308646001 = wellness, otherwise ambulatory.
- code and description are type[0].coding[0].code and .display; the reason is reasonCode[0].coding[0] in R4 and reason[0].coding[0] in STU3.
- The acquirer's text has every comma replaced by a space. Payer and the three cost columns are not in the resource: return NULL.""",
    "conditions": """- start and stop dates are the first 10 characters of onsetDateTime and abatementDateTime (the local date, not the UTC date).
- patient is subject.reference and the encounter is encounter.reference (R4) or context.reference (STU3), both without the urn:uuid: prefix.
- code and description are code.coding[0].code and .display; the acquirer's text has every comma replaced by a space.""",
    "procedures": """- start and stop are performedPeriod.start and .end (or performedDateTime for both); they carry a UTC offset and the contract wants UTC.
- patient is subject.reference, the encounter is encounter.reference (R4) or context.reference (STU3), without the urn:uuid: prefix.
- code and description are code.coding[0]; commas in text become spaces. The reason is the code of the Condition that reasonReference[0].reference points to. The cost is not in the resource: NULL.""",
    "medications": """- start is authoredOn (UTC). The resource has no end date: stop is NULL.
- patient is subject.reference, the encounter is encounter.reference (R4) or context.reference (STU3), without the urn:uuid: prefix.
- code and description are medicationCodeableConcept.coding[0]; when the request has a medicationReference instead, they are code.coding[0] of that Medication resource. Commas in text become spaces.
- The reason is the code of the Condition that reasonReference[0].reference points to. Payer, costs and dispenses are not in the resource: NULL.""",
    "observations": """- One row per value: an Observation with component[] gives one row per component (code and value from the component, date, patient, encounter and category from the parent); an Observation without components gives one row.
- date is effectiveDateTime (UTC); patient is subject.reference, the encounter is encounter.reference (R4) or context.reference (STU3), without the urn:uuid: prefix; category is category[0].coding[0].code.
- A valueQuantity gives type numeric, units = valueQuantity.unit and the value as text with exactly one decimal digit (163.34 is written 163.3, 71 is written 71.0). Other values give type text: the display of valueCodeableConcept.coding[0], or valueString.
- In DuckDB write (x->'$.path') IS NULL with the parentheses. Commas in text become spaces.""",
    "immunizations": """- date is occurrenceDateTime (R4) or date (STU3), in UTC; patient is patient.reference and the encounter is encounter.reference, without the urn:uuid: prefix.
- code and description are vaccineCode.coding[0]; commas in text become spaces. The cost is not in the resource: NULL.""",
    "allergies": """- start date is the first 10 characters of recordedDate (R4) or assertedDate (STU3); there is no stop date.
- patient is patient.reference without the urn:uuid: prefix. The resource has no encounter reference: use the patient's Encounter whose period.start equals that timestamp.
- code and description are code.coding[0]; system is SNOMED-CT or RxNorm according to the coding system URL; type is type; category is category[0].
- reaction 1 and 2 are reaction[0] and reaction[1]: manifestation[0].coding[0].code and .display, severity in upper case. Commas in text become spaces.""",
}

_CLAIMS = {
    "patients": """- raw_claims.members has one row per member: "Member id" is the patient id, "Date of birth", "Date of death", "Gender code", "Race code" and "Ethnicity" are already written as the acquirer writes them.
- "Name" is first name, a space, last name. State, county and zip are the Home_ columns. Everything else in the contract is not in the export: NULL.""",
    "conditions": """- Diagnoses are claim lines with "Diagnosis code" filled; the patient is "Patient account number". The same diagnosis appears on many lines (later visits and drugs name it as their reason): return one row per patient, code, "Service (from) date" and "Service to date".
- The start date is "Service (from) date"; the stop date is "Service to date", where 1969-12-31 means no stop date. There is no encounter id: NULL.""",
    "procedures": """- Procedures are claim lines with "Procedure code" filled; the patient is "Patient account number"; code and description are "Procedure code" and "Procedure description".
- The export has a date but no time: use "Procedure date" for both start and stop. There is no encounter id, cost or reason: NULL.""",
    "medications": """- Drugs are claim lines with "National drug code" filled (the column holds the RxNorm code the acquirer uses); the patient is "Patient account number".
- start is "Service (from) date" and stop is "Service to date", where 1969-12-31 means no stop. The export has dates without times.
- The reason is "Diagnosis code" and "Diagnosis description" of the same line. The payer identifier of the export is not one of the acquirer's payer ids and there is no encounter id: NULL for both.""",
}


def staging_hint(con, fmt: str, d: str) -> str:
    if fmt in ("fhir_r4", "fhir_stu3"):
        return _FHIR[d]
    if fmt == "claims":
        return _CLAIMS[d]
    cols = dialects.columns(con, d)
    if fmt == "d1":
        return (f"- The table is raw_d1.{dialects.D1_TABLE[d]}. Only names differ from the acquirer's source table "
                f"(values and types are the same). Raw column = acquirer source column:\n"
                + "\n".join(f"  {dialects.D1_COL[c]} = {c}" for c, _ in cols))
    if fmt == "d2":
        lines = ["- Timestamps are split into <column>_date (MM/DD/YYYY) and <column>_time (HH:MM:SS), both in UTC.",
                 "- Date columns are text written DD-Mon-YYYY (03-Sep-1942)."]
        names = [c for c, _ in cols]
        if "CODE" in names and "DESCRIPTION" in names:
            lines.append("- code_display is the code, ' | ', then the description: split at the first ' | '.")
        if "REASONCODE" in names:
            lines.append("- reason is the reason code, ' | ', then the reason description (NULL when there is no reason).")
        if d == "patients":
            lines.append("- full_name is 'LAST, FIRST'. city_state_zip is 'CITY, STATE ZIP'; the five-digit ZIP can be missing.")
        if d == "encounters":
            lines.append("- The three cost columns are in raw_d2.encounter_charges, joined on encounter_id = id.")
        lines.append("- All other columns keep the acquirer's source column names in lower case.")
        return "\n".join(lines)
    lines = []
    for c, pre in dialects.D3_PREFIX.get(d, {}).items():
        lines.append(f"- {c} carries the prefix '{pre}': strip it.")
    for c, lst in dialects.D3_LISTED.get(d, {}).items():
        lines.append(f"- {c} holds local codes: translate with raw_d3.code_map where list_name = '{lst}' "
                     f"(local_code to standard_value).")
    if d == "observations":
        lines.append("- Numeric values with units g, m and mg/L were converted from the acquirer's kg (x 1000), cm (x 0.01) and "
                     "mg/dL (x 10): convert the value back and restore the unit. Values are text with at least one decimal digit "
                     "(70.0, not 70).")
    lines.append("- Column names and all other values are as in the acquirer's source table.")
    return "\n".join(lines)


VISIT_LABEL = {"9201": "inpatient visit", "9202": "outpatient visit", "9203": "emergency room visit", "0": "no matching concept"}


def raw_form(fam: str, product: str, cat: str) -> str:
    if product == "dp_condition_flags":
        return {"fhir": f"http://snomed.info/sct|{cat}", "claims": f"{cat} (Diagnosis code type SNOMED)",
                "dialect": f"SCT:{cat}"}[fam]
    if product == "dp_latest_labs":
        return {"fhir": f"http://loinc.org|{cat}", "claims": cat, "dialect": f"LN:{cat}"}[fam]
    if product == "dp_utilisation_yearly":
        return f"{cat} ({VISIT_LABEL.get(str(cat), 'visit concept')})"
    return str(cat)


def inventory(con, fam: str, product: str, acquired: dict, known: dict) -> dict:
    if not acquired:
        return {"text": "As absorbed from this format, the acquired data has no rows that feed this product.",
                "hint": "- No category value is new: the model stays as it is."}
    new = sorted(str(k) for k in acquired if k not in known)
    old = sorted((str(k) for k in acquired if k in known), key=lambda k: (-acquired[k], k))
    lines = ["value as it appears in the acquired data | acquired patients | acquirer already has this value"]
    rows = [(raw_form(fam, product, k), acquired[k], "no") for k in new] + [(raw_form(fam, product, k), acquired[k], "yes") for k in old[:20]]
    rows.sort(key=lambda r: r[0])
    lines += [f"{a} | {b} | {c}" for a, b, c in rows]
    if len(old) > 20:
        lines.append(f"({len(old) - 20} further values that the acquirer already has are not listed)")
    hint = ["- The standard code is the part after the last '|' or ':' of the value; in the claims export the code is given as it is."
            if product in ("dp_condition_flags", "dp_latest_labs") else "- Values are already in the form the product uses."]
    if new:
        hint.append("- Values marked 'no' and their standard codes: " + "; ".join(f"{raw_form(fam, product, k)} = {k}" for k in new))
    else:
        hint.append("- No value is marked 'no': the model stays as it is.")
    return {"text": "\n".join(lines), "hint": "\n".join(hint)}
