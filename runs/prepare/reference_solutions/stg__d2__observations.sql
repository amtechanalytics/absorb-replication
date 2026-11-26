-- reference integration: d2 / observations
WITH acq_src AS (
    select
        cast(inv."DATE" as TIMESTAMP WITH TIME ZONE) as "DATE"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CATEGORY" as VARCHAR) as "CATEGORY"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."VALUE" as VARCHAR) as "VALUE"
        , cast(inv."UNITS" as VARCHAR) as "UNITS"
        , cast(inv."TYPE" as VARCHAR) as "TYPE"
    from (
select cast(strptime(date_date || ' ' || date_time, '%m/%d/%Y %H:%M:%S') as timestamp) at time zone 'UTC' as "DATE", "patient" as "PATIENT", "encounter" as "ENCOUNTER", "category" as "CATEGORY", split_part(code_display, ' | ', 1) as "CODE", nullif(substr(code_display, length(split_part(code_display, ' | ', 1)) + 4), '') as "DESCRIPTION", "value" as "VALUE", "units" as "UNITS", "type" as "TYPE" from {{ source('raw_d2', 'observations') }}
    ) as inv
)

, cte_observations_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_observations_rename AS (

    SELECT
        {{ timestamptz_to_naive(adapter.quote("date")) }} AS observation_datetime
        , patient AS patient_id
        , encounter AS encounter_id
        , category AS observation_category
        , code AS observation_code
        , description AS observation_description
        , {{ adapter.quote("value") }} AS observation_value
        , units AS observation_units
        , {{ adapter.quote("type") }} AS observation_value_type
    FROM cte_observations_lower

)

, cte_observation_date_columns AS (

    SELECT
        observation_datetime
        , {{ dbt.cast("observation_datetime", api.Column.translate_type("date")) }} AS observation_date
        , patient_id
        , encounter_id
        , observation_category
        , observation_code
        , observation_description
        , observation_value
        , observation_units
        , observation_value_type
    FROM cte_observations_rename

)

SELECT *
FROM cte_observation_date_columns
