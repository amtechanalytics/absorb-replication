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
