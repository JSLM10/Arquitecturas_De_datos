-- Falla si la suma de ventas del mart de QuickSight no coincide con la de fct_sales.
select *
from (
    select
        (select sum(subtotal) from {{ ref('fct_sales') }}) as fact_total,
        (select sum(ventas_totales) from {{ ref('mart_ventas_diarias') }}) as mart_total
) as totals
where {{ is_distinct_from('fact_total', 'mart_total') }}
