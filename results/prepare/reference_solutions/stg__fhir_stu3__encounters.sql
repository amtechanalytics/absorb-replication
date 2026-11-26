-- reference integration: fhir_stu3 / encounters
WITH acq_src AS (
    select
        cast(inv."Id" as VARCHAR) as "Id"
        , cast(inv."START" as TIMESTAMP WITH TIME ZONE) as "START"
        , cast(inv."STOP" as TIMESTAMP WITH TIME ZONE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ORGANIZATION" as VARCHAR) as "ORGANIZATION"
        , cast(inv."PROVIDER" as VARCHAR) as "PROVIDER"
        , cast(inv."PAYER" as VARCHAR) as "PAYER"
        , cast(inv."ENCOUNTERCLASS" as VARCHAR) as "ENCOUNTERCLASS"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."BASE_ENCOUNTER_COST" as FLOAT) as "BASE_ENCOUNTER_COST"
        , cast(inv."TOTAL_CLAIM_COST" as FLOAT) as "TOTAL_CLAIM_COST"
        , cast(inv."PAYER_COVERAGE" as FLOAT) as "PAYER_COVERAGE"
        , cast(inv."REASONCODE" as VARCHAR) as "REASONCODE"
        , cast(inv."REASONDESCRIPTION" as VARCHAR) as "REASONDESCRIPTION"
    from (
select
    e.resource->>'$.id' as "Id"
    , e.resource->>'$.period.start' as "START"
    , e.resource->>'$.period.end' as "STOP"
    , replace(e.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , split_part(e.resource->>'$.serviceProvider.reference', '|', 2) as "ORGANIZATION"
    , pr."Id" as "PROVIDER"
    , cast(null as varchar) as "PAYER"
    , case
        when e.resource->>'$.class.code' = 'EMER' then 'emergency'
        when e.resource->>'$.class.code' = 'IMP' then 'inpatient'
        when e.resource->>'$.type[0].coding[0].code' = '702927004' then 'urgentcare'
        when e.resource->>'$.type[0].coding[0].code' in ('162673000', '410620009', '308646001') then 'wellness'
        else 'ambulatory'
    end as "ENCOUNTERCLASS"
    , e.resource->>'$.type[0].coding[0].code' as "CODE"
    , replace(e.resource->>'$.type[0].coding[0].display', ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_ENCOUNTER_COST"
    , cast(null as float) as "TOTAL_CLAIM_COST"
    , cast(null as float) as "PAYER_COVERAGE"
    , e.resource->>'$.reason[0].coding[0].code' as "REASONCODE"
    , replace(e.resource->>'$.reason[0].coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_stu3', 'encounter') }} as e
left join (
    select "NAME", "ORGANIZATION", min("Id") as "Id"
    from {{ source('raw_fhir_stu3', 'providers') }}
    group by 1, 2
    having count(*) = 1
) as pr
    on pr."NAME" = regexp_replace(e.resource->>'$.participant[0].individual.display', '^Dr\. ', '')
    and pr."ORGANIZATION" = split_part(e.resource->>'$.serviceProvider.reference', '|', 2)
    ) as inv
)

, cte_encounters_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_encounters_rename AS (

    SELECT
        id AS encounter_id
        , {{ timestamptz_to_naive(adapter.quote("start")) }} AS encounter_start_datetime
        -- default to start date if stop date is null
        , COALESCE(
            {{ timestamptz_to_naive(adapter.quote("stop")) }},
            {{ timestamptz_to_naive(adapter.quote("start")) }}
        ) AS encounter_stop_datetime
        , patient AS patient_id
        , organization AS organization_id
        , provider AS provider_id
        , payer AS payer_id
        , encounterclass AS encounter_class
        , code AS encounter_code
        , description AS encounter_description
        , base_encounter_cost
        , total_claim_cost AS total_encounter_cost
        , payer_coverage AS encounter_payer_coverage
        , reasoncode AS encounter_reason_code
        , reasondescription AS encounter_reason_description
    FROM cte_encounters_lower

)

, cte_encounters_date_columns AS (

    SELECT
        encounter_id
        , encounter_start_datetime
        , {{ dbt.cast("encounter_start_datetime", api.Column.translate_type("date")) }} AS encounter_start_date
        , encounter_stop_datetime
        , COALESCE(
            {{ dbt.cast("encounter_start_datetime", api.Column.translate_type("date")) }},
            {{ dbt.cast("encounter_stop_datetime", api.Column.translate_type("date")) }}
        ) AS encounter_stop_date
        , patient_id
        , organization_id
        , provider_id
        , payer_id
        , encounter_class
        , encounter_code
        , encounter_description
        , base_encounter_cost
        , total_encounter_cost
        , encounter_payer_coverage
        , encounter_reason_code
        , encounter_reason_description
    FROM cte_encounters_rename

)

SELECT *
FROM cte_encounters_date_columns
