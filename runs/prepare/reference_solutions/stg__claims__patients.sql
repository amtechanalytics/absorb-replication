-- reference integration: claims / patients
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
    "Member id" as "Id"
    , "Date of birth" as "BIRTHDATE"
    , "Date of death" as "DEATHDATE"
    , cast(null as varchar) as "SSN"
    , cast(null as varchar) as "DRIVERS"
    , cast(null as varchar) as "PASSPORT"
    , cast(null as varchar) as "PREFIX"
    , split_part("Name", ' ', 1) as "FIRST"
    , split_part("Name", ' ', 2) as "LAST"
    , cast(null as varchar) as "SUFFIX"
    , cast(null as varchar) as "MAIDEN"
    , cast(null as varchar) as "MARITAL"
    , "Race code" as "RACE"
    , "Ethnicity" as "ETHNICITY"
    , "Gender code" as "GENDER"
    , cast(null as varchar) as "BIRTHPLACE"
    , cast(null as varchar) as "ADDRESS"
    , cast(null as varchar) as "CITY"
    , "Home_State" as "STATE"
    , "Home_County" as "COUNTY"
    , "Home_Zip code" as "ZIP"
    , cast(null as float) as "LAT"
    , cast(null as float) as "LON"
    , cast(null as float) as "HEALTHCARE_EXPENSES"
    , cast(null as float) as "HEALTHCARE_COVERAGE"
from {{ source('raw_claims', 'members') }}
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
