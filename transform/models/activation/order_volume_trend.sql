{{ config(order_by=['day']) }}
-- Publica raw.order_volume_trend_forecast (Gradient Boosting autoregressivo,
-- training/orders/train_order_volume_trend.py) em activation/ -- só
-- tabelas de activation/ chegam no serving store via
-- export_to_serving_store.py.
select
    day,
    actual_order_count,
    predicted_order_count,
    trend_label,
    is_forecast,
    trained_at
from {{ source('raw', 'order_volume_trend_forecast') }}
order by day
