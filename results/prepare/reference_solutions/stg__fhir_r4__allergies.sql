-- reference integration: fhir_r4 / allergies
WITH acq_src AS (
    select
        cast(inv."START" as DATE) as "START"
        , cast(inv."STOP" as DATE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."SYSTEM" as VARCHAR) as "SYSTEM"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."TYPE" as VARCHAR) as "TYPE"
        , cast(inv."CATEGORY" as VARCHAR) as "CATEGORY"
        , cast(inv."REACTION1" as VARCHAR) as "REACTION1"
        , cast(inv."DESCRIPTION1" as VARCHAR) as "DESCRIPTION1"
        , cast(inv."SEVERITY1" as VARCHAR) as "SEVERITY1"
        , cast(inv."REACTION2" as VARCHAR) as "REACTION2"
        , cast(inv."DESCRIPTION2" as VARCHAR) as "DESCRIPTION2"
        , cast(inv."SEVERITY2" as VARCHAR) as "SEVERITY2"
    from (
select
    cast(substr(a.resource->>'$.recordedDate', 1, 10) as date) as "START"
    , cast(null as date) as "STOP"
    , replace(a.resource->>'$.patient.reference', 'urn:uuid:', '') as "PATIENT"
    , en.encounter_id as "ENCOUNTER"
    , a.resource->>'$.code.coding[0].code' as "CODE"
    , case
        when a.resource->>'$.code.coding[0].system' like '%snomed%' then 'SNOMED-CT'
        when a.resource->>'$.code.coding[0].system' like '%rxnorm%' then 'RxNorm'
        else a.resource->>'$.code.coding[0].system'
    end as "SYSTEM"
    , replace(a.resource->>'$.code.coding[0].display', ',', ' ') as "DESCRIPTION"
    , a.resource->>'$.type' as "TYPE"
    , a.resource->>'$.category[0]' as "CATEGORY"
    , a.resource->>'$.reaction[0].manifestation[0].coding[0].code' as "REACTION1"
    , replace(a.resource->>'$.reaction[0].manifestation[0].coding[0].display', ',', ' ') as "DESCRIPTION1"
    , upper(a.resource->>'$.reaction[0].severity') as "SEVERITY1"
    , a.resource->>'$.reaction[1].manifestation[0].coding[0].code' as "REACTION2"
    , replace(a.resource->>'$.reaction[1].manifestation[0].coding[0].display', ',', ' ') as "DESCRIPTION2"
    , upper(a.resource->>'$.reaction[1].severity') as "SEVERITY2"
from {{ source('raw_fhir_r4', 'allergyintolerance') }} as a
left join (
    -- the allergy record carries no encounter reference: use the patient's encounter that starts at the same instant
    select
        resource->>'$.subject.reference' as patient_ref
        , resource->>'$.period.start' as started
        , min(resource->>'$.id') as encounter_id
    from {{ source('raw_fhir_r4', 'encounter') }}
    group by 1, 2
) as en
    on en.patient_ref = a.resource->>'$.patient.reference'
    and en.started = a.resource->>'$.recordedDate'
    ) as inv
)

, cte_allergies_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_allergies_rename AS (

    SELECT
        {{ adapter.quote("start") }} AS allergy_start_date
        , {{ adapter.quote("stop") }} AS allergy_stop_date
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS allergy_code
        , {{ adapter.quote("system") }} AS allergy_code_system
        , description AS allergy_description
        , {{ adapter.quote("type") }} AS allergy_type
        , category AS allergy_category
        , reaction1 AS reaction_1_code
        , description1 AS reaction_1_description
        , severity1 AS reaction_1_severity
        , reaction2 AS reaction_2_code
        , description2 AS reaction_2_description
        , severity2 AS reaction_2_severity
    FROM cte_allergies_lower

)

SELECT *
FROM cte_allergies_rename
