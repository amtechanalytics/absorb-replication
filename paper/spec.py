"""Study constants: domains, formats, tasks, scored tables and the size of the population."""
from __future__ import annotations

import os

DOMAINS = ["patients", "encounters", "conditions", "procedures", "medications", "observations",
           "immunizations", "allergies"]
FORMATS = ["fhir_r4", "fhir_stu3", "claims", "d1", "d2", "d3"]
FORMAT_DOMAINS = {
    "fhir_r4": DOMAINS, "fhir_stu3": DOMAINS, "d1": DOMAINS, "d2": DOMAINS, "d3": DOMAINS,
    "claims": ["patients", "conditions", "procedures", "medications"],
}
FAMILY_OF = {"fhir_r4": "fhir", "fhir_stu3": "fhir", "claims": "claims", "d1": "dialect", "d2": "dialect",
             "d3": "dialect"}
# the world a wide-product task is evaluated in: the acquired data absorbed by the reference integrations
FAMILY_WORLD = {"fhir": "fhir_r4", "claims": "claims", "dialect": "d3"}
PRODUCTS = ["dp_condition_flags", "dp_latest_labs", "dp_utilisation_yearly", "dp_coverage_months"]
ARMS = ["A1", "A2", "A3"]
SAMPLES = 2
MAX_REPAIR_TURNS = 2

# Population (the approved numbers). ABSORB_DEV_* shrink it for development runs only.
N_REQUEST = int(os.environ.get("ABSORB_DEV_REQUEST", "600"))
N_ACQUIRER = int(os.environ.get("ABSORB_DEV_ACQUIRER", "480"))
N_ACQUIRED = int(os.environ.get("ABSORB_DEV_ACQUIRED", "120"))
SEED = 20261116
REFERENCE_DATE = "20261101"
STATE = "Massachusetts"
N_ONLY_CONDITIONS = 6          # condition codes that occur only in the acquired group
N_ONLY_LABS = 4                # laboratory codes that occur only in the acquired group
ONLY_CARRIER_CAP = 0.75        # share of the acquired group that may be carriers of such codes

SOURCE_TABLES = ["allergies", "careplans", "claims", "claims_transactions", "conditions", "devices", "encounters",
                 "imaging_studies", "immunizations", "medications", "observations", "organizations", "patients",
                 "payer_transitions", "payers", "procedures", "providers", "supplies"]
PATIENT_COLUMN = {"patients": "Id", "claims": "PATIENTID", "claims_transactions": "PATIENTID"}
SHARED_TABLES = ["organizations", "providers", "payers"]

SCHEMA = "dbt_synthea_dev"
SRC_SCHEMA = SCHEMA + "_synthea_seeds"

# Scored tables: natural key columns (after the natural projection, see paper/score.py)
SCORED = {
    "person": ["person_id"],
    "death": ["person_id"],
    "visit_occurrence": ["person_id", "visit_concept_id", "visit_start_date"],
    "visit_detail": ["person_id", "visit_detail_concept_id", "visit_detail_start_date"],
    "condition_occurrence": ["person_id", "condition_source_value", "condition_start_date"],
    "procedure_occurrence": ["person_id", "procedure_source_value", "procedure_date"],
    "drug_exposure": ["person_id", "drug_source_value", "drug_exposure_start_date"],
    "measurement": ["person_id", "measurement_source_value", "measurement_date"],
    "observation": ["person_id", "observation_source_value", "observation_date"],
    "observation_period": ["person_id"],
    "condition_era": ["person_id", "condition_concept_id", "condition_era_start_date"],
    "drug_era": ["person_id", "drug_concept_id", "drug_era_start_date"],
    "dp_condition_flags": ["person_id"],
    "dp_latest_labs": ["person_id"],
    "dp_utilisation_yearly": ["person_id", "visit_year"],
    "dp_coverage_months": ["person_id"],
}
PRIMARY_KEY = {t: t + "_id" for t in ["visit_occurrence", "visit_detail", "condition_occurrence",
                                     "procedure_occurrence", "drug_exposure", "measurement", "observation",
                                     "observation_period", "condition_era", "drug_era"]}

# Claims: OMOP columns the claims export cannot carry (no encounter identifier, dates without times, no
# address). Declared before any model call; excluded from the reference check and the scores of claims tasks
# and counted separately as format-unrecoverable.
CLAIMS_UNCARRIED = {
    "*": ["provider_id", "visit_occurrence_id", "visit_detail_id"],
    "person": ["location_id"],
    "condition_occurrence": ["condition_end_date"],
    "procedure_occurrence": ["procedure_datetime", "procedure_end_date", "procedure_end_datetime"],
    "drug_exposure": ["drug_exposure_start_datetime", "drug_exposure_end_datetime", "drug_exposure_end_date",
                      "verbatim_end_date", "days_supply"],
    "measurement": ["measurement_datetime", "measurement_time"],
    "observation": ["observation_datetime"],
}

REFCHECK_MIN_SHARE = 0.90
REFCHECK_MIN_TASKS = 44


def staging_tasks():
    return [("stg", f, d) for f in FORMATS for d in FORMAT_DOMAINS[f]]


def wide_tasks():
    return [("wide", fam, p) for p in PRODUCTS for fam in ("fhir", "claims", "dialect")]


def all_tasks():
    return staging_tasks() + wide_tasks()


def task_id(t) -> str:
    return "|".join(t)


def uncarried(table: str) -> set:
    return set(CLAIMS_UNCARRIED["*"]) | set(CLAIMS_UNCARRIED.get(table, []))
