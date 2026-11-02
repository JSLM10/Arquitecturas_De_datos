select
    {{ dbt_utils.star(ref('int_mysql__products__qa'), except=['rejection_reason']) }}
from {{ ref('int_mysql__products__qa') }}
where rejection_reason is null
