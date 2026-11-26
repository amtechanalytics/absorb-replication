-- reference integration: fhir_stu3 / medications
WITH acq_src AS (
    select
        cast(inv."START" as TIMESTAMP WITH TIME ZONE) as "START"
        , cast(inv."STOP" as TIMESTAMP WITH TIME ZONE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."PAYER" as VARCHAR) as "PAYER"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."BASE_COST" as FLOAT) as "BASE_COST"
        , cast(inv."PAYER_COVERAGE" as FLOAT) as "PAYER_COVERAGE"
        , cast(inv."DISPENSES" as FLOAT) as "DISPENSES"
        , cast(inv."TOTALCOST" as FLOAT) as "TOTALCOST"
        , cast(inv."REASONCODE" as VARCHAR) as "REASONCODE"
        , cast(inv."REASONDESCRIPTION" as VARCHAR) as "REASONDESCRIPTION"
    from (
select
    m.resource->>'$.authoredOn' as "START"
    , cast(null as timestamptz) as "STOP"
    , replace(m.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , cast(null as varchar) as "PAYER"
    , replace(m.resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , coalesce(m.resource->>'$.medicationCodeableConcept.coding[0].code', md.resource->>'$.code.coding[0].code') as "CODE"
    , replace(coalesce(m.resource->>'$.medicationCodeableConcept.coding[0].display', md.resource->>'$.code.coding[0].display'), ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , cast(null as float) as "PAYER_COVERAGE"
    , cast(null as float) as "DISPENSES"
    , cast(null as float) as "TOTALCOST"
    , rc.resource->>'$.code.coding[0].code' as "REASONCODE"
    , replace(rc.resource->>'$.code.coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_stu3', 'medicationrequest') }} as m
left join {{ source('raw_fhir_stu3', 'medication') }} as md
    on md.id = replace(m.resource->>'$.medicationReference.reference', 'urn:uuid:', '')
left join {{ source('raw_fhir_stu3', 'condition') }} as rc
    on rc.id = replace(m.resource->>'$.reasonReference[0].reference', 'urn:uuid:', '')
    ) as inv
)

, cte_medications_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_medications_rename AS (

    SELECT
        {{ timestamptz_to_naive(adapter.quote("start")) }} AS medication_start_datetime
        , {{ timestamptz_to_naive(adapter.quote("stop")) }} AS medication_stop_datetime
        , patient AS patient_id
        , payer AS payer_id
        , encounter AS encounter_id
        , code AS medication_code
        , description AS medication_description
        , base_cost AS medication_base_cost
        , payer_coverage AS medication_payer_coverage
        , dispenses
        , totalcost AS medication_total_cost
        , reasoncode AS medication_reason_code
        , reasondescription AS medication_reason_description
    FROM cte_medications_lower

)

, cte_medications_date_columns AS (

    SELECT
        medication_start_datetime
        , {{ dbt.cast("medication_start_datetime", api.Column.translate_type("date")) }} AS medication_start_date
        , medication_stop_datetime
        , {{ dbt.cast("medication_stop_datetime", api.Column.translate_type("date")) }} AS medication_stop_date
        , patient_id
        , payer_id
        , encounter_id
        , medication_code
        , medication_description
        , medication_base_cost
        , medication_payer_coverage
        , dispenses
        , medication_total_cost
        , medication_reason_code
        , medication_reason_description
    FROM cte_medications_rename

)

SELECT *
FROM cte_medications_date_columns
