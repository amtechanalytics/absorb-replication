-- reference integration: fhir_stu3 / procedures
WITH acq_src AS (
    select
        cast(inv."START" as TIMESTAMP WITH TIME ZONE) as "START"
        , cast(inv."STOP" as TIMESTAMP WITH TIME ZONE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."BASE_COST" as FLOAT) as "BASE_COST"
        , cast(inv."REASONCODE" as VARCHAR) as "REASONCODE"
        , cast(inv."REASONDESCRIPTION" as VARCHAR) as "REASONDESCRIPTION"
    from (
select
    coalesce(p.resource->>'$.performedPeriod.start', p.resource->>'$.performedDateTime') as "START"
    , coalesce(p.resource->>'$.performedPeriod.end', p.resource->>'$.performedDateTime') as "STOP"
    , replace(p.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(p.resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , p.resource->>'$.code.coding[0].code' as "CODE"
    , replace(p.resource->>'$.code.coding[0].display', ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , rc.resource->>'$.code.coding[0].code' as "REASONCODE"
    , replace(rc.resource->>'$.code.coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_stu3', 'procedure') }} as p
left join {{ source('raw_fhir_stu3', 'condition') }} as rc
    on rc.id = replace(p.resource->>'$.reasonReference[0].reference', 'urn:uuid:', '')
    ) as inv
)

, cte_procedures_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_procedures_rename AS (

    SELECT
        {{ timestamptz_to_naive(adapter.quote("start")) }} AS procedure_start_datetime
        , {{ timestamptz_to_naive(adapter.quote("stop")) }} AS procedure_stop_datetime
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS procedure_code
        , description AS procedure_description
        , base_cost AS procedure_base_cost
        , reasoncode AS procedure_reason_code
        , reasondescription AS procedure_reason_description
    FROM cte_procedures_lower

)

, cte_procedures_date_columns AS (

    SELECT
        procedure_start_datetime
        , {{ dbt.cast("procedure_start_datetime", api.Column.translate_type("date")) }} AS procedure_start_date
        , procedure_stop_datetime
        , {{ dbt.cast("procedure_stop_datetime", api.Column.translate_type("date")) }} AS procedure_stop_date
        , patient_id
        , encounter_id
        , procedure_code
        , procedure_description
        , procedure_base_cost
        , procedure_reason_code
        , procedure_reason_description
    FROM cte_procedures_rename

)

SELECT *
FROM cte_procedures_date_columns
