#!/usr/bin/env bash
# Escenarios de calidad, incrementalidad y recuperacion (Punto 8). Cada comando corre el escenario y
# deja en pantalla la evidencia (antes / despues) para tomarle captura.
#
#   bash scripts/aws/escenarios.sh reiniciar             deja Redshift y la bodega en cero y regenera las fuentes
#   bash scripts/aws/escenarios.sh carga-inicial         primer lote completo
#   bash scripts/aws/escenarios.sh defectuosos           rechazos con motivo y lote de origen
#   bash scripts/aws/escenarios.sh repetir-lote          reprocesa el ultimo lote: nada se duplica
#   bash scripts/aws/escenarios.sh nuevo-lote [N]        agrega el lote diario N a las fuentes y lo procesa
#   bash scripts/aws/escenarios.sh cambio-scd2           cambia ciudad de un cliente y categoria de un producto
#   bash scripts/aws/escenarios.sh fallo                 agrega el lote diario 2 y la carga falla a proposito
#   bash scripts/aws/escenarios.sh recuperar             reprocesa el lote que fallo
#   bash scripts/aws/escenarios.sh conciliar             ventas: origen valido vs modelo vs mart de QuickSight
#   bash scripts/aws/escenarios.sh lotes                 tabla de control ops.lotes

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPADRE=(bash "$RAIZ/scripts/aws/compadre.sh")

titulo() { printf '\n==================== %s ====================\n' "$1"; }
sql() { "${COMPADRE[@]}" sql "$1"; }
# Primer valor de una consulta de una sola celda.
valor() { "${COMPADRE[@]}" sql "$1" | sed -n 3p | tr -d '[:space:]'; }

conteos() {
  sql "select 'fct_sales' as tabla, count(*) as filas from marts.fct_sales
       union all select 'fct_reviews', count(*) from marts.fct_reviews
       union all select 'fct_navigation_events', count(*) from marts.fct_navigation_events
       union all select 'dim_customer (versiones)', count(*) from marts.dim_customer
       union all select 'dim_product (versiones)', count(*) from marts.dim_product
       order by 1"
}

lotes_de() {
  sql "select batch_id, entidad, modo, estado, filas_extraidas as extraidas, filas_cargadas as cargadas,
              marca_inferior, marca_superior, coalesce(left(error, 60), '') as error
       from ops.lotes where batch_id = '$1' order by entidad"
}

ultimo_lote() { valor "select max(batch_id) from ops.lotes"; }

case "${1:-}" in
  reiniciar)
    titulo "Reinicio: Redshift y bodega en cero"
    printf 'Esto BORRA los esquemas raw, intermediate, quarantine, marts y ops de Redshift, los archivos de\n'
    printf 's3://<bodega>/raw/ y vuelve a generar los datos de RDS y DocumentDB (semilla 42).\n'
    read -r -p "Escriba 'si' para continuar: " respuesta
    [[ "$respuesta" == "si" ]] || { printf 'Cancelado.\n'; exit 0; }
    for esquema in '"raw"' intermediate quarantine marts ops; do
      sql "drop schema if exists $esquema cascade" >/dev/null && printf 'Esquema %s borrado\n' "$esquema"
    done
    bucket="$(terraform -chdir="$RAIZ/terraform" output -no-color -raw bucket)"
    aws s3 rm "s3://$bucket/raw/" --recursive --profile user_cli --only-show-errors && printf 'Archivos de s3://%s/raw/ borrados\n' "$bucket"
    "${COMPADRE[@]}" fuentes generate_data
    "${COMPADRE[@]}" limpiar-airflow
    ;;

  carga-inicial)
    titulo "Escenario: carga inicial"
    "${COMPADRE[@]}" pipeline auto || exit 1
    lote="$(ultimo_lote)"
    titulo "Lote $lote en ops.lotes (modo completo / foto)"
    lotes_de "$lote"
    titulo "Datos disponibles en los modelos analiticos"
    conteos
    ;;

  defectuosos)
    titulo "Escenario: registros defectuosos (cuarentena con motivo y lote de origen)"
    sql "select 'mysql.customers' as origen, rejection_reason as motivo, _batch_id as lote, count(*) as filas from quarantine.quarantine_mysql__customers group by 1, 2, 3
         union all select 'mysql.products', rejection_reason, _batch_id, count(*) from quarantine.quarantine_mysql__products group by 1, 2, 3
         union all select 'mysql.orders', rejection_reason, _batch_id, count(*) from quarantine.quarantine_mysql__orders group by 1, 2, 3
         union all select 'mysql.order_items', rejection_reason, _batch_id, count(*) from quarantine.quarantine_mysql__order_items group by 1, 2, 3
         union all select 'mongodb.reviews', rejection_reason, _batch_id, count(*) from quarantine.quarantine_mongodb__reviews group by 1, 2, 3
         union all select 'mongodb.navigation_events', rejection_reason, _batch_id, count(*) from quarantine.quarantine_mongodb__navigation_events group by 1, 2, 3
         order by 1, 2"
    titulo "Ejemplo: pedidos rechazados, trazables hasta su lote y su fuente"
    sql "select order_id, customer_id, sales_channel, total, rejection_reason, _batch_id, _source
         from quarantine.quarantine_mysql__orders order by order_id"
    ;;

  repetir-lote)
    lote="$(valor "select max(batch_id) from ops.lotes where estado = 'procesado'")"
    [[ -n "$lote" ]] || { printf 'No hay lotes procesados todavia. Corra primero carga-inicial.\n'; exit 1; }
    titulo "Escenario: repeticion del lote exitoso $lote — ANTES"
    conteos
    sql "select count(*) as filas_raw_del_lote from \"raw\".mysql_order_items where _batch_id = '$lote'"
    "${COMPADRE[@]}" pipeline auto "$lote" || exit 1
    titulo "Repeticion del lote $lote — DESPUES (debe ser igual a ANTES)"
    conteos
    sql "select count(*) as filas_raw_del_lote from \"raw\".mysql_order_items where _batch_id = '$lote'"
    ;;

  nuevo-lote)
    numero="${2:-1}"
    titulo "Escenario: nuevo lote incremental (lote diario $numero) — ANTES"
    conteos
    "${COMPADRE[@]}" fuentes append_batch --batch-id "$numero" || exit 1
    "${COMPADRE[@]}" pipeline auto || exit 1
    lote="$(ultimo_lote)"
    titulo "Lote $lote: solo trae lo nuevo (modo incremental desde la marca anterior)"
    lotes_de "$lote"
    titulo "DESPUES: los hechos crecen con los registros nuevos"
    conteos
    ;;

  cambio-scd2)
    titulo "Escenario: cambio de un atributo historizado — ANTES"
    sql "select customer_id, city, department, valid_from, valid_to, is_current from marts.dim_customer where customer_id = 1 order by valid_from"
    sql "select product_id, category, valid_from, valid_to, is_current from marts.dim_product where product_id = 1 order by valid_from"
    "${COMPADRE[@]}" fuentes simulate_changes || exit 1
    "${COMPADRE[@]}" pipeline auto || exit 1
    titulo "DESPUES: version nueva vigente y cierre de la anterior (valid_to)"
    sql "select customer_id, city, department, valid_from, valid_to, is_current from marts.dim_customer where customer_id = 1 order by valid_from"
    sql "select product_id, category, valid_from, valid_to, is_current from marts.dim_product where product_id = 1 order by valid_from"
    ;;

  fallo)
    titulo "Escenario: fallo controlado en la carga (con 2 reintentos acotados) — ANTES"
    conteos
    # El lote que va a fallar trae registros nuevos (lote diario 2), asi se ve que no se pierden.
    "${COMPADRE[@]}" fuentes append_batch --batch-id 2 || exit 1
    "${COMPADRE[@]}" pipeline auto "" cargar_a_redshift && { printf 'Se esperaba un fallo y no ocurrio.\n'; exit 1; }
    lote="$(ultimo_lote)"
    titulo "El lote $lote quedo en 'extraido' con su error: no avanzo la marca"
    lotes_de "$lote"
    titulo "raw no tiene NINGUNA fila de ese lote (la carga se deshizo completa)"
    sql "select count(*) as filas_raw_del_lote from \"raw\".mysql_customers where _batch_id = '$lote'"
    printf '\nPara recuperarlo:  bash scripts/aws/escenarios.sh recuperar\n'
    ;;

  recuperar)
    lote="$(valor "select max(batch_id) from ops.lotes where error is not null and estado <> 'procesado'")"
    [[ -n "$lote" ]] || { printf 'No hay lotes fallidos para recuperar.\n'; exit 1; }
    titulo "Escenario: reejecucion del lote fallido $lote (desde S3, sin consultar las fuentes)"
    "${COMPADRE[@]}" pipeline auto "$lote" || exit 1
    titulo "El lote quedo procesado y sin error"
    lotes_de "$lote"
    titulo "Sin perdida ni duplicacion"
    conteos
    ;;

  conciliar)
    titulo "Conciliacion del indicador de ventas"
    sql "select
           (select sum(items.subtotal) from intermediate.int_mysql__order_items__valid as items
              inner join intermediate.int_mysql__orders__valid as orders on orders.order_id = items.order_id) as ventas_origen_validas,
           (select sum(subtotal) from marts.fct_sales) as ventas_fct_sales,
           (select sum(ventas_totales) from marts.mart_ventas_diarias) as ventas_mart_quicksight"
    ;;

  lotes)
    sql "select batch_id, entidad, modo, estado, filas_extraidas as extraidas, filas_cargadas as cargadas,
                marca_superior, extraido_en, cargado_en, procesado_en, coalesce(left(error, 50), '') as error
         from ops.lotes order by batch_id, entidad"
    ;;

  *)
    sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
