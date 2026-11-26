-- reference integration: fhir_stu3 / conditions
WITH acq_src AS (
    select
        cast(inv."START" as DATE) as "START"
        , cast(inv."STOP" as DATE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
    from (
select
    cast(substr(resource->>'$.onsetDateTime', 1, 10) as date) as "START"
    , cast(substr(resource->>'$.abatementDateTime', 1, 10) as date) as "STOP"
    , replace(resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , resource->>'$.code.coding[0].code' as "CODE"
    , replace(resource->>'$.code.coding[0].display', ',', ' ') as "DESCRIPTION"
from {{ source('raw_fhir_stu3', 'condition') }}
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
