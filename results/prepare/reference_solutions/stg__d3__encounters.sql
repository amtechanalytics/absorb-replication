-- reference integration: d3 / encounters
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
select t."Id" as "Id", t."START" as "START", t."STOP" as "STOP", t."PATIENT" as "PATIENT", t."ORGANIZATION" as "ORGANIZATION", t."PROVIDER" as "PROVIDER", t."PAYER" as "PAYER", coalesce(m_encounter_class.standard_value, t."ENCOUNTERCLASS") as "ENCOUNTERCLASS", substr(t."CODE", 5) as "CODE", t."DESCRIPTION" as "DESCRIPTION", t."BASE_ENCOUNTER_COST" as "BASE_ENCOUNTER_COST", t."TOTAL_CLAIM_COST" as "TOTAL_CLAIM_COST", t."PAYER_COVERAGE" as "PAYER_COVERAGE", substr(t."REASONCODE", 5) as "REASONCODE", t."REASONDESCRIPTION" as "REASONDESCRIPTION" from {{ source('raw_d3', 'encounters') }} t left join {{ source('raw_d3', 'code_map') }} m_encounter_class on m_encounter_class.list_name = 'encounter_class' and m_encounter_class.local_code = t."ENCOUNTERCLASS"
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
