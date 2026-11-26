select
    p.person_id
    , max(case when co.condition_source_value = '10509002' then 1 else 0 end) as cond_10509002
    , max(case when co.condition_source_value = '1121000119107' then 1 else 0 end) as cond_1121000119107
    , max(case when co.condition_source_value = '124171000119105' then 1 else 0 end) as cond_124171000119105
    , max(case when co.condition_source_value = '127295002' then 1 else 0 end) as cond_127295002
    , max(case when co.condition_source_value = '15777000' then 1 else 0 end) as cond_15777000
    , max(case when co.condition_source_value = '19169002' then 1 else 0 end) as cond_19169002
    , max(case when co.condition_source_value = '195662009' then 1 else 0 end) as cond_195662009
    , max(case when co.condition_source_value = '196416002' then 1 else 0 end) as cond_196416002
    , max(case when co.condition_source_value = '22298006' then 1 else 0 end) as cond_22298006
    , max(case when co.condition_source_value = '232353008' then 1 else 0 end) as cond_232353008
    , max(case when co.condition_source_value = '233678006' then 1 else 0 end) as cond_233678006
    , max(case when co.condition_source_value = '239872002' then 1 else 0 end) as cond_239872002
    , max(case when co.condition_source_value = '271737000' then 1 else 0 end) as cond_271737000
    , max(case when co.condition_source_value = '278860009' then 1 else 0 end) as cond_278860009
    , max(case when co.condition_source_value = '36971009' then 1 else 0 end) as cond_36971009
    , max(case when co.condition_source_value = '389087006' then 1 else 0 end) as cond_389087006
    , max(case when co.condition_source_value = '398254007' then 1 else 0 end) as cond_398254007
    , max(case when co.condition_source_value = '40055000' then 1 else 0 end) as cond_40055000
    , max(case when co.condition_source_value = '410429000' then 1 else 0 end) as cond_410429000
    , max(case when co.condition_source_value = '44465007' then 1 else 0 end) as cond_44465007
    , max(case when co.condition_source_value = '444814009' then 1 else 0 end) as cond_444814009
    , max(case when co.condition_source_value = '446096008' then 1 else 0 end) as cond_446096008
    , max(case when co.condition_source_value = '53741008' then 1 else 0 end) as cond_53741008
    , max(case when co.condition_source_value = '55822004' then 1 else 0 end) as cond_55822004
    , max(case when co.condition_source_value = '59621000' then 1 else 0 end) as cond_59621000
    , max(case when co.condition_source_value = '62106007' then 1 else 0 end) as cond_62106007
    , max(case when co.condition_source_value = '68496003' then 1 else 0 end) as cond_68496003
    , max(case when co.condition_source_value = '74400008' then 1 else 0 end) as cond_74400008
    , max(case when co.condition_source_value = '82423001' then 1 else 0 end) as cond_82423001
    , max(case when co.condition_source_value = '110030002' then 1 else 0 end) as cond_110030002
    , max(case when co.condition_source_value = '185086009' then 1 else 0 end) as cond_185086009
    , max(case when co.condition_source_value = '22253000' then 1 else 0 end) as cond_22253000
    , max(case when co.condition_source_value = '25064002' then 1 else 0 end) as cond_25064002
    , max(case when co.condition_source_value = '33737001' then 1 else 0 end) as cond_33737001
    , max(case when co.condition_source_value = '427419006' then 1 else 0 end) as cond_427419006
from {{ ref('person') }} as p
left join {{ ref('condition_occurrence') }} as co
    on co.person_id = p.person_id
group by p.person_id
