-- reference integration: d1 / immunizations
WITH acq_src AS (
    select
        cast(inv."DATE" as TIMESTAMP WITH TIME ZONE) as "DATE"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."BASE_COST" as FLOAT) as "BASE_COST"
    from (
select event_ts as "DATE", member_ref as "PATIENT", visit_ref as "ENCOUNTER", concept_cd as "CODE", concept_label as "DESCRIPTION", unit_charge as "BASE_COST" from {{ source('raw_d1', 'vaccinations') }}
    ) as inv
)

, cte_immunizations_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_immunizations_rename AS (

    SELECT
        {{ timestamptz_to_naive(adapter.quote("date")) }} AS immunization_date
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS immunization_code
        , description AS immunization_description
        , base_cost AS immunization_base_cost
    FROM cte_immunizations_lower

)

SELECT *
FROM cte_immunizations_rename
