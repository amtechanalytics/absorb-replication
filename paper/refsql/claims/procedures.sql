select
    cast("Procedure date" as date) as "START"
    , cast("Procedure date" as date) as "STOP"
    , "Patient account number" as "PATIENT"
    , cast(null as varchar) as "ENCOUNTER"
    , "Procedure code" as "CODE"
    , "Procedure description" as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , cast(null as varchar) as "REASONCODE"
    , cast(null as varchar) as "REASONDESCRIPTION"
from {{ source('raw_claims', 'claims') }}
where "Procedure code" is not null
