-- reference integration: claims / conditions
WITH acq_src AS (
    select
        cast(inv."START" as DATE) as "START"
        , cast(inv."STOP" as DATE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
    from (
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
    ) as inv
)

, cte_conditions_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_conditions_rename AS (

    SELECT
        {{ adapter.quote("start") }} AS condition_start_date
        , {{ adapter.quote("stop") }} AS condition_stop_date
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS condition_code
        , description AS condition_description
    FROM cte_conditions_lower

)

SELECT *
FROM cte_conditions_rename
