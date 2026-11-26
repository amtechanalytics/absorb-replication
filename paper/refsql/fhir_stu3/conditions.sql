select
    cast(substr(resource->>'$.onsetDateTime', 1, 10) as date) as "START"
    , cast(substr(resource->>'$.abatementDateTime', 1, 10) as date) as "STOP"
    , replace(resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(resource->>'$.context.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , resource->>'$.code.coding[0].code' as "CODE"
    , replace(resource->>'$.code.coding[0].display', ',', ' ') as "DESCRIPTION"
from {{ source('raw_fhir_stu3', 'condition') }}
