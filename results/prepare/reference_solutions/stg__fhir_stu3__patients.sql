-- reference integration: fhir_stu3 / patients
WITH acq_src AS (
    select
        cast(inv."Id" as VARCHAR) as "Id"
        , cast(inv."BIRTHDATE" as DATE) as "BIRTHDATE"
        , cast(inv."DEATHDATE" as DATE) as "DEATHDATE"
        , cast(inv."SSN" as VARCHAR) as "SSN"
        , cast(inv."DRIVERS" as VARCHAR) as "DRIVERS"
        , cast(inv."PASSPORT" as VARCHAR) as "PASSPORT"
        , cast(inv."PREFIX" as VARCHAR) as "PREFIX"
        , cast(inv."FIRST" as VARCHAR) as "FIRST"
        , cast(inv."LAST" as VARCHAR) as "LAST"
        , cast(inv."SUFFIX" as VARCHAR) as "SUFFIX"
        , cast(inv."MAIDEN" as VARCHAR) as "MAIDEN"
        , cast(inv."MARITAL" as VARCHAR) as "MARITAL"
        , cast(inv."RACE" as VARCHAR) as "RACE"
        , cast(inv."ETHNICITY" as VARCHAR) as "ETHNICITY"
        , cast(inv."GENDER" as VARCHAR) as "GENDER"
        , cast(inv."BIRTHPLACE" as VARCHAR) as "BIRTHPLACE"
        , cast(inv."ADDRESS" as VARCHAR) as "ADDRESS"
        , cast(inv."CITY" as VARCHAR) as "CITY"
        , cast(inv."STATE" as VARCHAR) as "STATE"
        , cast(inv."COUNTY" as VARCHAR) as "COUNTY"
        , cast(inv."ZIP" as VARCHAR) as "ZIP"
        , cast(inv."LAT" as FLOAT) as "LAT"
        , cast(inv."LON" as FLOAT) as "LON"
        , cast(inv."HEALTHCARE_EXPENSES" as FLOAT) as "HEALTHCARE_EXPENSES"
        , cast(inv."HEALTHCARE_COVERAGE" as FLOAT) as "HEALTHCARE_COVERAGE"
    from (
select
    resource->>'$.id' as "Id"
    , resource->>'$.birthDate' as "BIRTHDATE"
    , cast(substr(resource->>'$.deceasedDateTime', 1, 10) as date) as "DEATHDATE"
    , list_filter(cast(resource->'$.identifier' as json[]), lambda i: i->>'$.type.coding[0].code' = 'SS')[1]->>'$.value' as "SSN"
    , list_filter(cast(resource->'$.identifier' as json[]), lambda i: i->>'$.type.coding[0].code' = 'DL')[1]->>'$.value' as "DRIVERS"
    , list_filter(cast(resource->'$.identifier' as json[]), lambda i: i->>'$.type.coding[0].code' = 'PPN')[1]->>'$.value' as "PASSPORT"
    , list_filter(cast(resource->'$.name' as json[]), lambda n: n->>'$.use' = 'official')[1]->>'$.prefix[0]' as "PREFIX"
    , list_filter(cast(resource->'$.name' as json[]), lambda n: n->>'$.use' = 'official')[1]->>'$.given[0]' as "FIRST"
    , list_filter(cast(resource->'$.name' as json[]), lambda n: n->>'$.use' = 'official')[1]->>'$.family' as "LAST"
    , list_filter(cast(resource->'$.name' as json[]), lambda n: n->>'$.use' = 'official')[1]->>'$.suffix[0]' as "SUFFIX"
    , list_filter(cast(resource->'$.name' as json[]), lambda n: n->>'$.use' = 'maiden')[1]->>'$.family' as "MAIDEN"
    , resource->>'$.maritalStatus.coding[0].code' as "MARITAL"
    , case list_filter(cast(resource->'$.extension' as json[]), lambda e: e->>'$.url' like '%us-core-race')[1]->>'$.extension[0].valueCoding.display'
        when 'White' then 'white'
        when 'Black or African American' then 'black'
        when 'Asian' then 'asian'
        when 'American Indian or Alaska Native' then 'native'
        when 'Native Hawaiian or Other Pacific Islander' then 'hawaiian'
        else 'other'
    end as "RACE"
    , case list_filter(cast(resource->'$.extension' as json[]), lambda e: e->>'$.url' like '%us-core-ethnicity')[1]->>'$.extension[0].valueCoding.display'
        when 'Hispanic or Latino' then 'hispanic'
        else 'nonhispanic'
    end as "ETHNICITY"
    , case resource->>'$.gender' when 'male' then 'M' when 'female' then 'F' end as "GENDER"
    , concat_ws('  '
        , list_filter(cast(resource->'$.extension' as json[]), lambda e: e->>'$.url' like '%irthPlace')[1]->>'$.valueAddress.city'
        , list_filter(cast(resource->'$.extension' as json[]), lambda e: e->>'$.url' like '%irthPlace')[1]->>'$.valueAddress.state'
        , list_filter(cast(resource->'$.extension' as json[]), lambda e: e->>'$.url' like '%irthPlace')[1]->>'$.valueAddress.country'
    ) as "BIRTHPLACE"
    , resource->>'$.address[0].line[0]' as "ADDRESS"
    , resource->>'$.address[0].city' as "CITY"
    , coalesce(st.state_name, resource->>'$.address[0].state') as "STATE"
    , cast(null as varchar) as "COUNTY"
    , resource->>'$.address[0].postalCode' as "ZIP"
    , list_filter(cast(resource->'$.address[0].extension[0].extension' as json[]), lambda g: g->>'$.url' = 'latitude')[1]->>'$.valueDecimal' as "LAT"
    , list_filter(cast(resource->'$.address[0].extension[0].extension' as json[]), lambda g: g->>'$.url' = 'longitude')[1]->>'$.valueDecimal' as "LON"
    , cast(null as float) as "HEALTHCARE_EXPENSES"
    , cast(null as float) as "HEALTHCARE_COVERAGE"
from {{ source('raw_fhir_stu3', 'patient') }}
left join {{ ref('stg_map__states') }} as st
    on st.state_abbreviation = resource->>'$.address[0].state'
    ) as inv
)

, cte_patients_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_patients_rename AS (

    SELECT
        id AS patient_id
        , birthdate AS birth_date
        , deathdate AS death_date
        , ssn
        , drivers AS drivers_license_number
        , passport AS passport_number
        , prefix AS patient_prefix
        , {{ adapter.quote("first") }} AS patient_first_name
        , {{ adapter.quote("last") }} AS patient_last_name
        , suffix AS patient_suffix
        , maiden AS maiden_name
        , marital AS marital_status
        , race
        , ethnicity
        , gender AS patient_gender
        , birthplace
        , address AS patient_address
        , city AS patient_city
        , state AS patient_state
        , county AS patient_county
        , zip AS patient_zip
        , lat AS patient_latitude
        , lon AS patient_longitude
        , healthcare_expenses
        , healthcare_coverage
    FROM cte_patients_lower

)

SELECT *
FROM cte_patients_rename
