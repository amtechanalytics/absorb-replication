with ranked as (
    select
        m.person_id
        , m.measurement_source_value
        , m.value_as_number
        , row_number() over (
            partition by m.person_id, m.measurement_source_value
            order by m.measurement_datetime desc, m.value_as_number desc
        ) as rn
    from {{ ref('measurement') }} as m
    where m.value_as_number is not null
)

select
    p.person_id
    , max(case when l.measurement_source_value = '18262-6' then l.value_as_number end) as lab_18262_6
    , max(case when l.measurement_source_value = '20565-8' then l.value_as_number end) as lab_20565_8
    , max(case when l.measurement_source_value = '2069-3' then l.value_as_number end) as lab_2069_3
    , max(case when l.measurement_source_value = '2085-9' then l.value_as_number end) as lab_2085_9
    , max(case when l.measurement_source_value = '2093-3' then l.value_as_number end) as lab_2093_3
    , max(case when l.measurement_source_value = '21000-5' then l.value_as_number end) as lab_21000_5
    , max(case when l.measurement_source_value = '2339-0' then l.value_as_number end) as lab_2339_0
    , max(case when l.measurement_source_value = '2571-8' then l.value_as_number end) as lab_2571_8
    , max(case when l.measurement_source_value = '29463-7' then l.value_as_number end) as lab_29463_7
    , max(case when l.measurement_source_value = '2947-0' then l.value_as_number end) as lab_2947_0
    , max(case when l.measurement_source_value = '32207-3' then l.value_as_number end) as lab_32207_3
    , max(case when l.measurement_source_value = '32623-1' then l.value_as_number end) as lab_32623_1
    , max(case when l.measurement_source_value = '38483-4' then l.value_as_number end) as lab_38483_4
    , max(case when l.measurement_source_value = '39156-5' then l.value_as_number end) as lab_39156_5
    , max(case when l.measurement_source_value = '4544-3' then l.value_as_number end) as lab_4544_3
    , max(case when l.measurement_source_value = '59576-9' then l.value_as_number end) as lab_59576_9
    , max(case when l.measurement_source_value = '6690-2' then l.value_as_number end) as lab_6690_2
    , max(case when l.measurement_source_value = '718-7' then l.value_as_number end) as lab_718_7
    , max(case when l.measurement_source_value = '72514-3' then l.value_as_number end) as lab_72514_3
    , max(case when l.measurement_source_value = '777-3' then l.value_as_number end) as lab_777_3
    , max(case when l.measurement_source_value = '785-6' then l.value_as_number end) as lab_785_6
    , max(case when l.measurement_source_value = '786-4' then l.value_as_number end) as lab_786_4
    , max(case when l.measurement_source_value = '787-2' then l.value_as_number end) as lab_787_2
    , max(case when l.measurement_source_value = '789-8' then l.value_as_number end) as lab_789_8
    , max(case when l.measurement_source_value = '8302-2' then l.value_as_number end) as lab_8302_2
    , max(case when l.measurement_source_value = '8310-5' then l.value_as_number end) as lab_8310_5
    , max(case when l.measurement_source_value = '8462-4' then l.value_as_number end) as lab_8462_4
    , max(case when l.measurement_source_value = '8480-6' then l.value_as_number end) as lab_8480_6
    , max(case when l.measurement_source_value = '8867-4' then l.value_as_number end) as lab_8867_4
    , max(case when l.measurement_source_value = '9279-1' then l.value_as_number end) as lab_9279_1
    , max(case when l.measurement_source_value = '19926-5' then l.value_as_number end) as lab_19926_5
    , max(case when l.measurement_source_value = '33756-8' then l.value_as_number end) as lab_33756_8
    , max(case when l.measurement_source_value = '57905-2' then l.value_as_number end) as lab_57905_2
from {{ ref('person') }} as p
left join ranked as l
    on l.person_id = p.person_id and l.rn = 1
group by p.person_id
