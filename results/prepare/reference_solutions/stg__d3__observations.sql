-- reference integration: d3 / observations
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
select t."DATE" as "DATE", t."PATIENT" as "PATIENT", t."ENCOUNTER" as "ENCOUNTER", t."CATEGORY" as "CATEGORY", substr(t."CODE", 4) as "CODE", t."DESCRIPTION" as "DESCRIPTION", case when t."TYPE"='numeric' and t."UNITS"='m' then cast(cast(cast(t."VALUE" as decimal(28,10)) / cast(0.01 as decimal(12,4)) as double) as varchar) when t."TYPE"='numeric' and t."UNITS"='g' then cast(cast(cast(t."VALUE" as decimal(28,10)) / cast(1000 as decimal(12,4)) as double) as varchar) when t."TYPE"='numeric' and t."UNITS"='mg/L' then cast(cast(cast(t."VALUE" as decimal(28,10)) / cast(10 as decimal(12,4)) as double) as varchar) else t."VALUE" end as "VALUE", case when t."TYPE"='numeric' and t."UNITS"='m' then 'cm' when t."TYPE"='numeric' and t."UNITS"='g' then 'kg' when t."TYPE"='numeric' and t."UNITS"='mg/L' then 'mg/dL' else t."UNITS" end as "UNITS", t."TYPE" as "TYPE" from {{ source('raw_d3', 'observations') }} t
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
