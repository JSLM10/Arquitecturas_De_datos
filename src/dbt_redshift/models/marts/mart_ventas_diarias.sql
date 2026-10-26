-- Tabla para QuickSight: ventas por fecha, categoria (la vigente el dia de la venta), canal y departamento.
-- Una fila por combinacion. Es una tabla "plana" para que el dashboard no necesite escribir joins.
select
    dates.date as fecha,
    dates.year as anio,
    dates.month as mes,
    product.category as categoria,
    channel.sales_channel as canal,
    coalesce(geography.department, 'Sin departamento') as departamento,
    count(*) as lineas_de_venta,
    sum(sales.quantity) as unidades,
    sum(sales.subtotal) as ventas_totales
from {{ ref('fct_sales') }} as sales
inner join {{ ref('dim_date') }} as dates on dates.date_sk = sales.date_sk
inner join {{ ref('dim_product') }} as product on product.product_sk = sales.product_sk
inner join {{ ref('dim_sales_channel') }} as channel on channel.sales_channel_sk = sales.sales_channel_sk
left join {{ ref('dim_geography') }} as geography on geography.geography_sk = sales.geography_sk
group by 1, 2, 3, 4, 5, 6
