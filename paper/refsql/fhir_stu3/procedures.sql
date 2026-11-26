select
    coalesce(p.resource->>'$.performedPeriod.start', p.resource->>'$.performedDateTime') as "START"
    , coalesce(p.resource->>'$.performedPeriod.end', p.resource->>'$.performedDateTime') as "STOP"
    , replace(p.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(p.resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , p.resource->>'$.code.coding[0].code' as "CODE"
    , replace(p.resource->>'$.code.coding[0].display', ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , rc.resource->>'$.code.coding[0].code' as "REASONCODE"
    , replace(rc.resource->>'$.code.coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_stu3', 'procedure') }} as p
left join {{ source('raw_fhir_stu3', 'condition') }} as rc
    on rc.id = replace(p.resource->>'$.reasonReference[0].reference', 'urn:uuid:', '')
