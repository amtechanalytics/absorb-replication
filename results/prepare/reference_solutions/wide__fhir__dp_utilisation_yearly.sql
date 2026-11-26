select
    v.person_id
    , extract(year from v.visit_start_date) as visit_year
    , count(case when v.visit_concept_id = 9201 then 1 end) as visits_9201
    , count(case when v.visit_concept_id = 9202 then 1 end) as visits_9202
    , count(case when v.visit_concept_id = 9203 then 1 end) as visits_9203
from {{ ref('visit_occurrence') }} as v
group by v.person_id, extract(year from v.visit_start_date)
