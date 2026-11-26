select
    resource->>'$.date' as "DATE"
    , replace(resource->>'$.patient.reference', 'urn:uuid:', '') as "PATIENT"
    , replace(resource->>'$.encounter.reference', 'urn:uuid:', '') as "ENCOUNTER"
    , resource->>'$.vaccineCode.coding[0].code' as "CODE"
    , replace(resource->>'$.vaccineCode.coding[0].display', ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
from {{ source('raw_fhir_stu3', 'immunization') }}
