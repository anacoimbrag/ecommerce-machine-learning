{{ config(order_by=['day']) }}
-- Feature view para training/revenue/train_revenue_trend.py. Receita líquida
-- agregada por dia (bruta - reembolsos do dia), grão 1 linha por dia com
-- pelo menos um pedido.
with orders_by_day as (
    select
        -- assumeNotNull: sem isso o ORDER BY (day) do MergeTree quebra com
        -- "Sorting key contains nullable columns" -- toDate() de uma coluna
        -- Nullable(DateTime) continua Nullable(Date) mesmo depois do filtro
        -- `where purchased_at is not null` acima.
        toDate(assumeNotNull(purchased_at)) as day,
        sum(revenue) as gross_revenue,
        count(*) as order_count
    from {{ source('staging', 'stg_customer_orders') }}
    where purchased_at is not null
    group by 1
),

refunds_by_day as (
    select
        toDate(refunded_at) as day,
        sum(refund_value) as refund_value
    from {{ source('staging', 'stg_customer_refunds') }}
    group by 1
)

select
    o.day as day,
    o.order_count as order_count,
    o.gross_revenue - coalesce(r.refund_value, 0) as net_revenue
from orders_by_day o
left join refunds_by_day r on o.day = r.day
order by o.day
