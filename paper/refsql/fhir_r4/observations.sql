with single as (
    select
        resource
        , resource->'$.code' as code
        , resource as val
    from {{ source('raw_fhir_r4', 'observation') }}
    where (resource->'$.component') is null
)

, parts as (
    select
        o.resource
        , c.comp->'$.code' as code
        , c.comp as val
    from {{ source('raw_fhir_r4', 'observation') }} as o
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
    , replace(resource->>'$.encounter.reference', 'urn:uuid:', '') as "ENCOUNTER"
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
