#!/usr/bin/env bash
# Escenarios de calidad, incrementalidad y recuperación del data lake. Cada uno imprime su evidencia.
#
#   bash data-lake/scripts/escenarios.sh reiniciar           deja el lago en cero (Bronze, Silver, Gold y control)
#   bash data-lake/scripts/escenarios.sh carga-inicial       primera ingesta real de los tres feeds
#   bash data-lake/scripts/escenarios.sh defectuosos         rechazos con motivo y archivo de Bronze
#   bash data-lake/scripts/escenarios.sh repetir-lote        reprocesa una corrida ya publicada
#   bash data-lake/scripts/escenarios.sh nuevo-lote          noticias nuevas sin reprocesar las existentes
#   bash data-lake/scripts/escenarios.sh modificado          una noticia cambia de texto
#   bash data-lake/scripts/escenarios.sh fallo               la publicación falla a propósito
#   bash data-lake/scripts/escenarios.sh recuperar           reejecuta la corrida que falló
#   bash data-lake/scripts/escenarios.sh reconstruir         rehace Silver y Gold desde Bronze
#   bash data-lake/scripts/escenarios.sh nueva-particion     fecha nueva: visible en Athena al registrar la partición
#   bash data-lake/scripts/escenarios.sh fuente-caida        una fuente falla: la corrida queda parcial
#   bash data-lake/scripts/escenarios.sh todos               corre los ocho escenarios y muestra un resumen
#   bash data-lake/scripts/escenarios.sh evidencia           archivos de Bronze, Silver y Gold
#   bash data-lake/scripts/escenarios.sh consultas           consultas de Athena y bytes escaneados

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPADRE=(bash "$RAIZ/scripts/compadre.sh")
VEREDICTO=""

titulo() { printf '\n==================== %s ====================\n' "$1"; }
sql() { "${COMPADRE[@]}" sql "$1"; }
valor() { sql "$1" | sed -n 3p | tr -d '[:space:]'; }
cli() { "${COMPADRE[@]}" cli "$@"; }
correr() { "${COMPADRE[@]}" pipeline "$@"; }
noticias() { valor "select count(*) from silver_news"; }
sin_enriquecer() {
  valor "select count(*) from silver_news n where not exists (select 1 from silver_news_entities e where e.news_id = n.news_id) and not exists (select 1 from silver_news_key_phrases k where k.news_id = n.news_id)"
}
estado_corrida() {
  sql "select run_id, fuente, etapa, estado, items_recibidos as recibidos, nuevas, repetidas, actualizadas, rechazadas, substr(coalesce(error, ''), 1, 55) as error from ops_lotes where run_id like '$1%' order by run_id, fuente"
}
linea_log() { "${COMPADRE[@]}" log "$1" 40 | grep -E "$2" | tail -1 | sed 's/^\[[^]]*\] *//'; }

carga_inicial() {
  titulo "Carga inicial"
  correr || return 1
  estado_corrida "$(cli ultima publicada)"
  sql "select (select count(*) from silver_news) as noticias, (select count(*) from silver_news_entities) as entidades, (select count(*) from silver_news_key_phrases) as frases, (select count(*) from gold_noticias_por_dia) as filas_gold"
  VEREDICTO="Bronze, Silver y Gold publicados; Athena ve $(noticias) noticias"
}

defectuosos() {
  titulo "Registros defectuosos"
  local run
  run="$(cli copia defectuosa | tail -1)"
  correr reprocesar_run="$run" || return 1
  sql "select motivo, fuente, substr(titulo, 1, 30) as titulo, bronze_key from silver_cuarentena where run_id = '$run' order by motivo"
  estado_corrida "$run"
  VEREDICTO="$(valor "select count(*) from silver_cuarentena where run_id = '$run'") rechazos con motivo y archivo de Bronze (esperados: 4)"
}

repetir_lote() {
  titulo "Repetición de un lote exitoso"
  local run antes despues gantes gdespues
  run="$(cli ultima publicada)"
  antes="$(noticias)"
  gantes="$(valor "select coalesce(sum(noticias), 0) from gold_noticias_por_dia")"
  printf 'Antes: Silver %s noticias, Gold %s\n' "$antes" "$gantes"
  correr reprocesar_run="$run" || return 1
  despues="$(noticias)"
  gdespues="$(valor "select coalesce(sum(noticias), 0) from gold_noticias_por_dia")"
  printf 'Después: Silver %s noticias, Gold %s\n\n' "$despues" "$gdespues"
  estado_corrida "$run+reproceso"
  VEREDICTO="Silver $antes -> $despues y Gold $gantes -> $gdespues: sin duplicados ni doble conteo"
}

nuevo_lote() {
  titulo "Nuevo lote incremental"
  local run antes despues
  antes="$(noticias)"
  run="$(cli copia nuevas | tail -1)"
  correr reprocesar_run="$run" || return 1
  despues="$(noticias)"
  printf 'Silver: %s -> %s noticias\n\n' "$antes" "$despues"
  estado_corrida "$run"
  linea_log enriquecer_comprehend "Textos analizados"
  VEREDICTO="Silver $antes -> $despues: solo las $((despues - antes)) nuevas se enriquecieron"
}

modificado() {
  titulo "Noticia con contenido modificado"
  local run antes despues m_antes m_despues
  antes="$(noticias)"
  m_antes="$(valor "select count(*) from silver_news where titulo like '%(versión corregida)%'")"
  run="$(cli copia modificada | tail -1)"
  correr reprocesar_run="$run" || return 1
  despues="$(noticias)"
  m_despues="$(valor "select count(*) from silver_news where titulo like '%(versión corregida)%'")"
  sql "select substr(titulo, 1, 60) as titulo, substr(descripcion, 1, 50) as descripcion, ultima_ingesta_utc from silver_news where titulo like '%(versión corregida)%'"
  estado_corrida "$run"
  linea_log enriquecer_comprehend "Textos analizados"
  VEREDICTO="Silver $antes -> $despues; versión vigente actualizada ($m_antes -> $m_despues); 1 sola llamada nueva a Comprehend"
}

fallo() {
  titulo "Fallo controlado en publicar_silver"
  local run antes despues huerfanas
  antes="$(noticias)"
  run="$(cli copia nuevas --fuente deportes | tail -1)"
  if correr reprocesar_run="$run" simular_fallo=publicar_silver; then
    printf 'Se esperaba un fallo y no ocurrió.\n'
    return 1
  fi
  despues="$(noticias)"
  huerfanas="$(sin_enriquecer)"
  printf '\nSilver: %s -> %s noticias; sin entidades ni frases: %s\n\n' "$antes" "$despues" "$huerfanas"
  estado_corrida "$run"
  VEREDICTO="falla en publicar_silver: $huerfanas noticias sin entidades ni frases; la corrida $run no quedó publicada"
}

recuperar() {
  titulo "Reejecución de la corrida que falló"
  local run duplicados huerfanas
  run="$(cli ultima fallida | tail -1)"
  [[ -n "$run" ]] || { printf 'No hay corridas fallidas para recuperar.\n'; return 1; }
  printf 'Corrida a recuperar: %s\n' "$run"
  correr reprocesar_run="$run" || return 1
  duplicados="$(valor "select count(*) - count(distinct news_id) from silver_news")"
  huerfanas="$(sin_enriquecer)"
  printf '\nDuplicados en Silver: %s; sin entidades ni frases: %s\n\n' "$duplicados" "$huerfanas"
  estado_corrida "$run"
  VEREDICTO="corrida $run recuperada: $duplicados duplicados, $huerfanas noticias sin entidades ni frases"
}

reconstruir() {
  titulo "Reprocesamiento desde Bronze"
  local antes despues e_antes e_despues
  antes="$(noticias)"
  e_antes="$(valor "select count(*) from silver_news_entities")"
  correr reconstruir=true || return 1
  despues="$(noticias)"
  e_despues="$(valor "select count(*) from silver_news_entities")"
  printf '\nSilver: %s -> %s noticias; entidades: %s -> %s\n\n' "$antes" "$despues" "$e_antes" "$e_despues"
  linea_log limpiar_validar "Reconstruido"
  linea_log extraer_colombia "Omitida"
  VEREDICTO="Silver y Gold reconstruidos desde Bronze ($antes -> $despues noticias) sin consultar los RSS"
}

nueva_particion() {
  titulo "Nueva partición"
  local run antes despues
  run="$(cli copia particion | tail -1)"
  correr reprocesar_run="$run" registrar_glue=false || return 1
  antes="$(noticias)"
  printf '\nSin registrar la partición:\n'
  cli athena-cuenta
  printf '\nRegistrando la partición en Glue...\n'
  cli particiones >/dev/null
  despues="$(noticias)"
  printf '\nDespués de registrarla:\n'
  cli athena-cuenta
  VEREDICTO="Athena ve $antes noticias antes de registrar la partición y $despues después"
}

fuente_caida() {
  titulo "Fuente no disponible"
  correr fuente_caida=economia || return 1
  estado_corrida "$(cli ultima publicada)"
  VEREDICTO="economía quedó fallida (no 'sin noticias') y la corrida parcial"
}

todos() {
  local nombres=() resultados=() escenario
  for escenario in carga_inicial defectuosos repetir_lote nuevo_lote modificado fallo recuperar reconstruir nueva_particion; do
    VEREDICTO="NO TERMINÓ"
    "$escenario" || true
    nombres+=("${escenario//_/ }")
    resultados+=("$VEREDICTO")
  done
  titulo "Resumen de escenarios"
  for i in "${!nombres[@]}"; do
    printf '%-18s %s\n' "${nombres[$i]}" "${resultados[$i]}"
  done
}

case "${1:-}" in
  reiniciar)
    titulo "Reinicio: el lago queda en cero"
    printf 'Se borran Bronze, Silver, Gold, control y la caché de Comprehend del bucket, y el historial de Airflow.\n'
    read -r -p "Escriba 'si' para continuar: " respuesta
    [[ "$respuesta" == "si" ]] || { printf 'Cancelado.\n'; exit 0; }
    bucket="$(terraform -chdir="$RAIZ/terraform" output -no-color -raw bucket)"
    for prefijo in bronze silver gold control stage cache_comprehend athena-resultados; do
      aws s3 rm "s3://$bucket/$prefijo/" --recursive --only-show-errors --profile "${AWS_PROFILE:-user_cli}"
    done
    "${COMPADRE[@]}" limpiar-airflow
    cli particiones >/dev/null
    printf 'Listo.\n'
    ;;
  carga-inicial) carga_inicial ;;
  defectuosos) defectuosos ;;
  repetir-lote) repetir_lote ;;
  nuevo-lote) nuevo_lote ;;
  modificado) modificado ;;
  fallo) fallo ;;
  recuperar) recuperar ;;
  reconstruir) reconstruir ;;
  nueva-particion) nueva_particion ;;
  fuente-caida) fuente_caida ;;
  todos) todos ;;
  evidencia)
    cli arbol
    printf '\n'
    cli resumen
    ;;
  consultas)
    cli consultas
    printf '\n== Bytes escaneados con y sin filtro de partición\n'
    cli bytes
    ;;
  *)
    sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
