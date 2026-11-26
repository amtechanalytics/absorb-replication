-- reference integration: d1 / allergies
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
select begin_ts as "START", end_ts as "STOP", member_ref as "PATIENT", visit_ref as "ENCOUNTER", concept_cd as "CODE", code_scheme as "SYSTEM", concept_label as "DESCRIPTION", kind as "TYPE", grouping as "CATEGORY", rx1_cd as "REACTION1", rx1_label as "DESCRIPTION1", rx1_sev as "SEVERITY1", rx2_cd as "REACTION2", rx2_label as "DESCRIPTION2", rx2_sev as "SEVERITY2" from {{ source('raw_d1', 'allergy_list') }}
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
