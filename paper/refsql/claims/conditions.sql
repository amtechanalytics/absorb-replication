-- Diagnoses are claim lines with a diagnosis code. The export does not say which line records the onset of a
-- condition and which repeats it as the reason for a later visit or drug, so every distinct period is kept:
-- one row per patient, code, "Service (from) date" and "Service to date" (1969-12-31 means still open).
select distinct
    cast("Service (from) date" as date) as "START"
    , nullif(cast("Service to date" as date), date '1969-12-31') as "STOP"
    , "Patient account number" as "PATIENT"
    , cast(null as varchar) as "ENCOUNTER"
    , "Diagnosis code" as "CODE"
    , "Diagnosis description" as "DESCRIPTION"
from {{ source('raw_claims', 'claims') }}
where "Diagnosis code" is not null
