-- reference integration: d1 / conditions
WITH acq_src AS (
    select
        cast(inv."START" as DATE) as "START"
        , cast(inv."STOP" as DATE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
    from (
select begin_ts as "START", end_ts as "STOP", member_ref as "PATIENT", visit_ref as "ENCOUNTER", concept_cd as "CODE", concept_label as "DESCRIPTION" from {{ source('raw_d1', 'dx_history') }}
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
