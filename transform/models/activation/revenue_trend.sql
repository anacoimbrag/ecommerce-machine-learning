{{ config(order_by=['day']) }}
-- Publica raw.revenue_trend_forecast (Gradient Boosting autoregressivo,
-- training/revenue/train_revenue_trend.py) em activation/ -- só tabelas de
-- activation/ chegam no serving store via export_to_serving_store.py.
select
    day,
    actual_revenue,
    predicted_revenue,
    trend_label,
    is_forecast,
    trained_at
from {{ source('raw', 'revenue_trend_forecast') }}
order by day
