{{ config(order_by=['customer_id', 'promotion_id']) }}
-- Feature/label view para training/campaigns/train_propensity.py. Grão: 1 linha
-- por (customer_id, promotion_id) com exposição registrada (view/select de
-- promoção no GA4). O rótulo `converted` vem do uso real do cupom em
-- fct_order_line — não depende de activation.customer_profile (evita ciclo,
-- mesma razão de feat_rfm_features.sql).
with exposure as (
    select * from {{ ref('feat_promotion_engagement') }}
),

rfm as (
    select * from {{ ref('feat_rfm_features') }}
),

category_totals as (
    select customer_id, category, sum(quantity) as qty
    from {{ source('staging', 'stg_customer_order_items') }}
    group by 1, 2
),
favorite_category as (
    select customer_id, category as favorite_category
    from (
        select customer_id, category,
               row_number() over (partition by customer_id order by qty desc, category) as rn
        from category_totals
    )
    where rn = 1
),

brand_totals as (
    select customer_id, brand, sum(quantity) as qty
    from {{ source('staging', 'stg_customer_order_items') }}
    group by 1, 2
),
favorite_brand as (
    select customer_id, brand as favorite_brand
    from (
        select customer_id, brand,
               row_number() over (partition by customer_id order by qty desc, brand) as rn
        from brand_totals
    )
    where rn = 1
),

conversions as (
    select distinct customer_id, promotion_id
    from {{ source('marts', 'fct_order_line') }}
    where promotion_id is not null
)

select
    e.customer_id as customer_id,
    e.promotion_slug as promotion_id,
    e.view_count as view_count,
    e.select_count as select_count,
    dateDiff('day', e.last_seen_at, now()) as days_since_last_exposure,
    -- 730 (a janela toda de dados) em vez de um sentinela gigante (999999):
    -- sem padronização, um valor tão fora de escala dominava o z da
    -- regressão logística sozinho. Quem nunca comprou já fica marcado por
    -- has_purchase_history — não precisa de um número "impossível" aqui.
    coalesce(r.recency_days, 730) as recency_days,
    coalesce(r.has_purchase_history, false) as has_purchase_history,
    coalesce(r.total_orders, 0) as total_orders,
    coalesce(r.net_revenue, 0) as net_revenue,
    r.avg_order_value as avg_order_value,
    fc.favorite_category as favorite_category,
    fb.favorite_brand as favorite_brand,
    c.promotion_id is not null as converted
from exposure e
left join rfm r on e.customer_id = r.customer_id
left join favorite_category fc on e.customer_id = fc.customer_id
left join favorite_brand fb on e.customer_id = fb.customer_id
left join conversions c
    on e.customer_id = c.customer_id and e.promotion_slug = c.promotion_id
