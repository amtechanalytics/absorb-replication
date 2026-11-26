-- reference integration: d3 / patients
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
select t."Id" as "Id", t."BIRTHDATE" as "BIRTHDATE", t."DEATHDATE" as "DEATHDATE", t."SSN" as "SSN", t."DRIVERS" as "DRIVERS", t."PASSPORT" as "PASSPORT", t."PREFIX" as "PREFIX", t."FIRST" as "FIRST", t."LAST" as "LAST", t."SUFFIX" as "SUFFIX", t."MAIDEN" as "MAIDEN", coalesce(m_marital.standard_value, t."MARITAL") as "MARITAL", coalesce(m_race.standard_value, t."RACE") as "RACE", coalesce(m_ethnicity.standard_value, t."ETHNICITY") as "ETHNICITY", coalesce(m_gender.standard_value, t."GENDER") as "GENDER", t."BIRTHPLACE" as "BIRTHPLACE", t."ADDRESS" as "ADDRESS", t."CITY" as "CITY", t."STATE" as "STATE", t."COUNTY" as "COUNTY", t."ZIP" as "ZIP", t."LAT" as "LAT", t."LON" as "LON", t."HEALTHCARE_EXPENSES" as "HEALTHCARE_EXPENSES", t."HEALTHCARE_COVERAGE" as "HEALTHCARE_COVERAGE" from {{ source('raw_d3', 'patients') }} t left join {{ source('raw_d3', 'code_map') }} m_marital on m_marital.list_name = 'marital' and m_marital.local_code = t."MARITAL" left join {{ source('raw_d3', 'code_map') }} m_race on m_race.list_name = 'race' and m_race.local_code = t."RACE" left join {{ source('raw_d3', 'code_map') }} m_ethnicity on m_ethnicity.list_name = 'ethnicity' and m_ethnicity.local_code = t."ETHNICITY" left join {{ source('raw_d3', 'code_map') }} m_gender on m_gender.list_name = 'gender' and m_gender.local_code = t."GENDER"
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
