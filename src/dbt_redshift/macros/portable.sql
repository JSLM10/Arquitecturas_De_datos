{# Macros que reemplazan lo que DuckDB hacia con funciones propias y Redshift no tiene o llama distinto. #}

{# Ultima version de cada llave en raw. raw acumula todos los lotes (cada fila trae su _batch_id); el
   batch_id esta ordenado por fecha UTC, asi que el mayor es el mas reciente. #}
{% macro latest_by_key(relation, key) %}
(
    select ranked.*
    from (
        select
            rows_in_raw.*,
            row_number() over (
                partition by rows_in_raw.{{ key }}
                order by rows_in_raw._batch_id desc, rows_in_raw._loaded_at desc
            ) as _version_rank
        from {{ relation }} as rows_in_raw
    ) as ranked
    where ranked._version_rank = 1
)
{% endmacro %}

{# a IS DISTINCT FROM b, que Redshift no admite: comparacion que trata NULL como un valor mas. #}
{% macro is_distinct_from(left_value, right_value) %}
(
    ({{ left_value }} <> {{ right_value }})
    or ({{ left_value }} is null and {{ right_value }} is not null)
    or ({{ left_value }} is not null and {{ right_value }} is null)
)
{% endmacro %}

{# Hora local de negocio (Bogota) de una columna timestamptz. En DuckDB era timezone(zona, columna). #}
{% macro to_business_time(column) %}
({{ column }} at time zone '{{ var("business_timezone") }}')
{% endmacro %}

{# Dia de la semana ISO (lunes = 1 ... domingo = 7). Redshift: extract(dow) va de domingo = 0 a sabado = 6. #}
{% macro iso_dow(column) %}
(mod(cast(extract(dow from {{ column }}) as integer) + 6, 7) + 1)
{% endmacro %}
