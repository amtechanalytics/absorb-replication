select
    cast("Service (from) date" as date) as "START"
    , nullif(cast("Service to date" as date), date '1969-12-31') as "STOP"
    , "Patient account number" as "PATIENT"
    , cast(null as varchar) as "PAYER"
    , cast(null as varchar) as "ENCOUNTER"
    , "National drug code" as "CODE"
    , cast(null as varchar) as "DESCRIPTION"
    , cast(null as float) as "BASE_COST"
    , cast(null as float) as "PAYER_COVERAGE"
    , cast(null as float) as "DISPENSES"
    , cast(null as float) as "TOTALCOST"
    , "Diagnosis code" as "REASONCODE"
    , "Diagnosis description" as "REASONDESCRIPTION"
from {{ source('raw_claims', 'claims') }}
where "National drug code" is not null
