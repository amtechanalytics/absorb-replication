select
    p.person_id
    , coalesce(sum(case when pp.plan_source_value = 'Aetna' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_aetna
    , coalesce(sum(case when pp.plan_source_value = 'Anthem' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_anthem
    , coalesce(sum(case when pp.plan_source_value = 'Blue Cross Blue Shield' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_blue_cross_blue_shield
    , coalesce(sum(case when pp.plan_source_value = 'Cigna Health' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_cigna_health
    , coalesce(sum(case when pp.plan_source_value = 'Dual Eligible' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_dual_eligible
    , coalesce(sum(case when pp.plan_source_value = 'Humana' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_humana
    , coalesce(sum(case when pp.plan_source_value = 'Medicaid' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_medicaid
    , coalesce(sum(case when pp.plan_source_value = 'Medicare' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_medicare
    , coalesce(sum(case when pp.plan_source_value = 'NO_INSURANCE' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_no_insurance
    , coalesce(sum(case when pp.plan_source_value = 'UnitedHealthcare' then datediff('month', pp.payer_plan_period_start_date, pp.payer_plan_period_end_date) end), 0) as months_unitedhealthcare
from {{ ref('person') }} as p
left join {{ ref('payer_plan_period') }} as pp
    on pp.person_id = p.person_id
group by p.person_id
