-- reference integration: d1 / medications
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
select begin_ts as "START", end_ts as "STOP", member_ref as "PATIENT", plan_ref as "PAYER", visit_ref as "ENCOUNTER", concept_cd as "CODE", concept_label as "DESCRIPTION", unit_charge as "BASE_COST", plan_paid as "PAYER_COVERAGE", fills as "DISPENSES", charge_total as "TOTALCOST", why_cd as "REASONCODE", why_label as "REASONDESCRIPTION" from {{ source('raw_d1', 'rx_orders') }}
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
