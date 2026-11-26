-- reference integration: fhir_stu3 / observations
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
with single as (
    select
        resource
        , resource->'$.code' as code
        , resource as val
    from {{ source('raw_fhir_stu3', 'observation') }}
    where (resource->'$.component') is null
)

, parts as (
    select
        o.resource
        , c.comp->'$.code' as code
        , c.comp as val
    from {{ source('raw_fhir_stu3', 'observation') }} as o
    , unnest(cast(o.resource->'$.component' as json[])) as c (comp)
    where (o.resource->'$.component') is not null
)

, both_kinds as (
    select * from single
    union all
    select * from parts
)

select
    resource->>'$.effectiveDateTime' as "DATE"
    , replace(resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , resource->>'$.category[0].coding[0].code' as "CATEGORY"
    , code->>'$.coding[0].code' as "CODE"
    , replace(code->>'$.coding[0].display', ',', ' ') as "DESCRIPTION"
    , case
        when (val->'$.valueQuantity') is not null then printf('%.1f', cast(val->>'$.valueQuantity.value' as double))
        when (val->'$.valueCodeableConcept') is not null then replace(val->>'$.valueCodeableConcept.coding[0].display', ',', ' ')
        when (val->'$.valueString') is not null then replace(val->>'$.valueString', ',', ' ')
        when (val->'$.valueBoolean') is not null then val->>'$.valueBoolean'
    end as "VALUE"
    , val->>'$.valueQuantity.unit' as "UNITS"
    , case when (val->'$.valueQuantity') is not null then 'numeric' else 'text' end as "TYPE"
from both_kinds
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
