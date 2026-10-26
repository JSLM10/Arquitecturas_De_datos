{# Filtro de cargas incrementales para la fila candidata (alias candidate). Carga las llaves nuevas, las filas cuya fecha de negocio cae en la ventana de reproceso (desde incremental_lookback_days antes de la fecha máxima ya cargada) y las filas cuyas llaves de dimensión resueltas cambiaron (tracked_columns), por ejemplo cuando una versión SCD2 nueva reemplaza a la anterior. #}
{# Version Redshift: Redshift no admite subconsultas correlacionadas dentro de un OR (el "or exists" de la
   version DuckDB). La misma logica se arma con un LEFT JOIN contra las filas ya cargadas: la llave es unica
   en la tabla de hechos, asi que el join no duplica filas candidatas. #}
{% macro incremental_candidate_filter(key_column, business_date_column, tracked_columns=[]) %}
{% if is_incremental() %}
left join (
    select {{ key_column }}{% for column in tracked_columns %}, {{ column }}{% endfor %}
    from {{ this }}
) as existing on existing.{{ key_column }} = candidate.{{ key_column }}
where existing.{{ key_column }} is null
or candidate.{{ business_date_column }} >= (
    select max(dates.date) - {{ var('incremental_lookback_days') }}
    from {{ this }} as loaded
    inner join {{ ref('dim_date') }} as dates on dates.date_sk = loaded.date_sk
)
{% for column in tracked_columns %}
or {{ is_distinct_from('existing.' ~ column, 'candidate.' ~ column) }}
{% endfor %}
{% endif %}
{% endmacro %}

{# Elimina de la tabla de hechos las filas cuya llave de origen ya no existe en la capa validada. #}
{% macro delete_orphaned_facts(sk_column, source_relation, source_key) %}
delete from {{ this }}
where {{ sk_column }} not in (
    select {{ dbt_utils.generate_surrogate_key(['cast(' ~ source_key ~ ' as varchar)']) }}
    from {{ source_relation }}
)
{% endmacro %}
