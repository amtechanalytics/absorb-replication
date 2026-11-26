-- reference integration: d2 / immunizations
WITH acq_src AS (
    select
        cast(inv."DATE" as TIMESTAMP WITH TIME ZONE) as "DATE"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."BASE_COST" as FLOAT) as "BASE_COST"
    from (
select cast(strptime(date_date || ' ' || date_time, '%m/%d/%Y %H:%M:%S') as timestamp) at time zone 'UTC' as "DATE", "patient" as "PATIENT", "encounter" as "ENCOUNTER", split_part(code_display, ' | ', 1) as "CODE", nullif(substr(code_display, length(split_part(code_display, ' | ', 1)) + 4), '') as "DESCRIPTION", "base_cost" as "BASE_COST" from {{ source('raw_d2', 'immunizations') }}
    ) as inv
)

, cte_immunizations_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_immunizations_rename AS (

    SELECT
        {{ timestamptz_to_naive(adapter.quote("date")) }} AS immunization_date
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS immunization_code
        , description AS immunization_description
        , base_cost AS immunization_base_cost
    FROM cte_immunizations_lower

)

SELECT *
FROM cte_immunizations_rename
