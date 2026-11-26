-- reference integration: d2 / procedures
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
select cast(strptime(start_date || ' ' || start_time, '%m/%d/%Y %H:%M:%S') as timestamp) at time zone 'UTC' as "START", cast(strptime(stop_date || ' ' || stop_time, '%m/%d/%Y %H:%M:%S') as timestamp) at time zone 'UTC' as "STOP", "patient" as "PATIENT", "encounter" as "ENCOUNTER", split_part(code_display, ' | ', 1) as "CODE", nullif(substr(code_display, length(split_part(code_display, ' | ', 1)) + 4), '') as "DESCRIPTION", "base_cost" as "BASE_COST", split_part(reason, ' | ', 1) as "REASONCODE", nullif(substr(reason, length(split_part(reason, ' | ', 1)) + 4), '') as "REASONDESCRIPTION" from {{ source('raw_d2', 'procedures') }}
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
