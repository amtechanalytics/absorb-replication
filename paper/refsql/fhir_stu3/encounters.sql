select
    e.resource->>'$.id' as "Id"
    , e.resource->>'$.period.start' as "START"
    , e.resource->>'$.period.end' as "STOP"
    , replace(e.resource->>'$.subject.reference', 'urn:uuid:', '') as "PATIENT"
    , split_part(e.resource->>'$.serviceProvider.reference', '|', 2) as "ORGANIZATION"
    , pr."Id" as "PROVIDER"
    , cast(null as varchar) as "PAYER"
    , case
        when e.resource->>'$.class.code' = 'EMER' then 'emergency'
        when e.resource->>'$.class.code' = 'IMP' then 'inpatient'
        when e.resource->>'$.type[0].coding[0].code' = '702927004' then 'urgentcare'
        when e.resource->>'$.type[0].coding[0].code' in ('162673000', '410620009', '308646001') then 'wellness'
        else 'ambulatory'
    end as "ENCOUNTERCLASS"
    , e.resource->>'$.type[0].coding[0].code' as "CODE"
    , replace(e.resource->>'$.type[0].coding[0].display', ',', ' ') as "DESCRIPTION"
    , cast(null as float) as "BASE_ENCOUNTER_COST"
    , cast(null as float) as "TOTAL_CLAIM_COST"
    , cast(null as float) as "PAYER_COVERAGE"
    , e.resource->>'$.reason[0].coding[0].code' as "REASONCODE"
    , replace(e.resource->>'$.reason[0].coding[0].display', ',', ' ') as "REASONDESCRIPTION"
from {{ source('raw_fhir_stu3', 'encounter') }} as e
left join (
    select "NAME", "ORGANIZATION", min("Id") as "Id"
    from {{ source('raw_fhir_stu3', 'providers') }}
    group by 1, 2
    having count(*) = 1
) as pr
    on pr."NAME" = regexp_replace(e.resource->>'$.participant[0].individual.display', '^Dr\. ', '')
    and pr."ORGANIZATION" = split_part(e.resource->>'$.serviceProvider.reference', '|', 2)
