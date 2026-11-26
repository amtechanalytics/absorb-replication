select
    m.resource->>'$.authoredOn' as "START"
    , cast(null as timestamptz) as "STOP"
    , replace(m.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , cast(null as varchar) as "PAYER"
    , replace(m.resource->>'$.encounter.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , coalesce(m.resource->>'$.medicationCodeableConcept.coding[0].code', md.resource->>'$.code.coding[0].code') as "CODE"
    , replace(coalesce(m.resource->>'$.medicationCodeableConcept.coding[0].display', md.resource->>'$.code.coding[0].display'), ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , cast(null as float) as "PAYER_COVERAGE"
    , cast(null as float) as "DISPENSES"
    , cast(null as float) as "TOTALCOST"
    , rc.resource->>'$.code.coding[0].code' as "REASONCODE"
    , replace(rc.resource->>'$.code.coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_r4', 'medicationrequest') }} as m
left join {{ source('raw_fhir_r4', 'medication') }} as md
    on md.id = replace(m.resource->>'$.medicationReference.reference', 'urn:uuid:', '')
left join {{ source('raw_fhir_r4', 'condition') }} as rc
    on rc.id = replace(m.resource->>'$.reasonReference[0].reference', 'urn:uuid:', '')
