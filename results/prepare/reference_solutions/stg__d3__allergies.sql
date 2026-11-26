-- reference integration: d3 / allergies
WITH acq_src AS (
    select
        cast(inv."START" as DATE) as "START"
        , cast(inv."STOP" as DATE) as "STOP"
        , cast(inv."PATIENT" as VARCHAR) as "PATIENT"
        , cast(inv."ENCOUNTER" as VARCHAR) as "ENCOUNTER"
        , cast(inv."CODE" as VARCHAR) as "CODE"
        , cast(inv."SYSTEM" as VARCHAR) as "SYSTEM"
        , cast(inv."DESCRIPTION" as VARCHAR) as "DESCRIPTION"
        , cast(inv."TYPE" as VARCHAR) as "TYPE"
        , cast(inv."CATEGORY" as VARCHAR) as "CATEGORY"
        , cast(inv."REACTION1" as VARCHAR) as "REACTION1"
        , cast(inv."DESCRIPTION1" as VARCHAR) as "DESCRIPTION1"
        , cast(inv."SEVERITY1" as VARCHAR) as "SEVERITY1"
        , cast(inv."REACTION2" as VARCHAR) as "REACTION2"
        , cast(inv."DESCRIPTION2" as VARCHAR) as "DESCRIPTION2"
        , cast(inv."SEVERITY2" as VARCHAR) as "SEVERITY2"
    from (
select t."START" as "START", t."STOP" as "STOP", t."PATIENT" as "PATIENT", t."ENCOUNTER" as "ENCOUNTER", substr(t."CODE", 5) as "CODE", t."SYSTEM" as "SYSTEM", t."DESCRIPTION" as "DESCRIPTION", t."TYPE" as "TYPE", t."CATEGORY" as "CATEGORY", t."REACTION1" as "REACTION1", t."DESCRIPTION1" as "DESCRIPTION1", t."SEVERITY1" as "SEVERITY1", t."REACTION2" as "REACTION2", t."DESCRIPTION2" as "DESCRIPTION2", t."SEVERITY2" as "SEVERITY2" from {{ source('raw_d3', 'allergies') }} t
    ) as inv
)

, cte_allergies_lower AS (

    SELECT
        *
    FROM acq_src
)

, cte_allergies_rename AS (

    SELECT
        {{ adapter.quote("start") }} AS allergy_start_date
        , {{ adapter.quote("stop") }} AS allergy_stop_date
        , patient AS patient_id
        , encounter AS encounter_id
        , code AS allergy_code
        , {{ adapter.quote("system") }} AS allergy_code_system
        , description AS allergy_description
        , {{ adapter.quote("type") }} AS allergy_type
        , category AS allergy_category
        , reaction1 AS reaction_1_code
        , description1 AS reaction_1_description
        , severity1 AS reaction_1_severity
        , reaction2 AS reaction_2_code
        , description2 AS reaction_2_description
        , severity2 AS reaction_2_severity
    FROM cte_allergies_lower

)

SELECT *
FROM cte_allergies_rename
