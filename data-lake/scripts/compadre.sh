#!/usr/bin/env bash
# Atajos para trabajar con el compadre (la EC2 del data lake). Usa los outputs de Terraform.
#
#   bash data-lake/scripts/compadre.sh estado                  está listo el compadre?
#   bash data-lake/scripts/compadre.sh entrar                  abre una sesión SSH
#   bash data-lake/scripts/compadre.sh desplegar               lleva el código y levanta Airflow
#   bash data-lake/scripts/compadre.sh pipeline [clave=valor]  dispara el DAG y espera (ver parámetros abajo)
#   bash data-lake/scripts/compadre.sh tareas                  estado de cada tarea de la última corrida
#   bash data-lake/scripts/compadre.sh log <tarea> [líneas]    log de una tarea
#   bash data-lake/scripts/compadre.sh cli <comando...>        herramientas del pipeline (ver noticias/cli.py)
#   bash data-lake/scripts/compadre.sh sql "<consulta>"        consulta en Athena
#   bash data-lake/scripts/compadre.sh programar on|off        ejecución horaria del DAG
#   bash data-lake/scripts/compadre.sh limpiar-airflow         borra el historial de corridas
#   bash data-lake/scripts/compadre.sh clave-airflow           muestra la clave de Airflow
#
# Parámetros de pipeline: reprocesar_run=<id> reconstruir=true registrar_glue=false
#                         simular_fallo=enriquecer|publicar_silver fuente_caida=<fuente>

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAVE="${LLAVE_SSH:-$HOME/.ssh/la-llave-dw}"
SSH_OPCIONES=(-i "$LLAVE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
COMPOSE='cd ~/lago && docker compose -f docker/docker-compose.yml --project-directory .'
DAG="noticias_datalake"

salida_tf() {
  local valor
  valor="$(terraform -chdir="$RAIZ/terraform" output -no-color -raw "$1" 2>/dev/null)" || return 1
  [[ "$valor" =~ ^[^[:space:]]+$ && "$valor" != "null" ]] || return 1
  printf '%s' "$valor"
}

comando="${1:-}"
case "$comando" in
  estado | entrar | desplegar | pipeline | tareas | log | cli | sql | programar | limpiar-airflow | clave-airflow) ;;
  *)
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac

ip="$(salida_tf ec2_ip_publica)" || {
  printf 'El compadre no está prendido. Ponga crear_ec2 = true en terraform/terraform.tfvars y corra terraform apply.\n' >&2
  exit 1
}
[[ -f "$LLAVE" ]] || { printf 'No encuentro la llave %s\n' "$LLAVE" >&2; exit 1; }

en_el_compadre() { ssh "${SSH_OPCIONES[@]}" "ec2-user@$ip" "$@"; }

sin_conexion() {
  printf '\nNo pude conectar al compadre (%s). Revise que su IP no haya cambiado (curl -s https://checkip.amazonaws.com), o espere un minuto si apenas arrancó.\n' "$ip" >&2
  exit 1
}

aws_en_airflow() { en_el_compadre "$COMPOSE exec -T airflow-scheduler $*"; }

case "$comando" in
  estado)
    en_el_compadre 'if [ -f /var/lib/cloud/instance/compadre-listo ]; then echo "El compadre está LISTO."; else echo "Todavía se está armando; repita en un minuto."; fi
docker --version
docker compose version' || sin_conexion
    ;;

  entrar)
    en_el_compadre || sin_conexion
    ;;

  desplegar)
    bucket="$(salida_tf bucket)" || exit 1
    base="$(salida_tf base_datos)" || exit 1
    grupo="$(salida_tf workgroup_athena)" || exit 1
    temporal="$(mktemp -d)"
    trap 'rm -rf "$temporal"' EXIT
    cat > "$temporal/publico.env" <<EOF
AWS_REGION=us-east-2
AIRFLOW_UID=1000
DL_BUCKET=$bucket
DL_BASE_DATOS=$base
DL_WORKGROUP=$grupo
EOF
    tar czf "$temporal/codigo.tgz" -C "$RAIZ" --exclude='__pycache__' docker src
    scp "${SSH_OPCIONES[@]}" -q "$temporal/codigo.tgz" "$temporal/publico.env" "ec2-user@$ip:~/" || sin_conexion
    en_el_compadre 'bash -s' <<'REMOTO'
set -euo pipefail
mkdir -p ~/lago
tar xzf ~/codigo.tgz -C ~/lago
cd ~/lago

# Las claves de Airflow se generan una vez y se quedan en la EC2 (permisos 600).
if [ ! -f .secretos ]; then
  umask 077
  {
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
    echo "AIRFLOW_FERNET_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    echo "AIRFLOW_SECRET_KEY=$(openssl rand -hex 24)"
    echo "AIRFLOW_ADMIN_USERNAME=airflow"
    echo "AIRFLOW_ADMIN_PASSWORD=$(openssl rand -hex 8)"
  } > .secretos
fi
programar="$(grep '^DL_PROGRAMAR=' .env 2>/dev/null || echo DL_PROGRAMAR=0)"
cat ~/publico.env .secretos > .env
echo "$programar" >> .env
chmod 600 .env .secretos

docker compose -f docker/docker-compose.yml --project-directory . up -d --build

printf 'Esperando a Airflow'
for _ in $(seq 1 60); do
  curl -fs http://localhost:8080/health >/dev/null 2>&1 && break
  printf '.'; sleep 5
done
for _ in $(seq 1 40); do
  docker compose -f docker/docker-compose.yml --project-directory . exec -T airflow-scheduler airflow dags list 2>/dev/null | grep -q noticias_datalake && break
  printf '.'; sleep 5
done
printf ' listo\n'
REMOTO
    printf 'Airflow: http://%s:8080 (usuario airflow). Clave: compadre.sh clave-airflow\n' "$ip"
    ;;

  pipeline)
    shift
    conf=""
    for par in "$@"; do
      clave="${par%%=*}"
      valor="${par#*=}"
      [[ "$valor" == true || "$valor" == false ]] && fragmento="\"$clave\": $valor" || fragmento="\"$clave\": \"$valor\""
      conf="${conf:+$conf, }$fragmento"
    done
    marca="$(date -u +'%Y-%m-%dT%H:%M:%S+00:00')"
    aws_en_airflow "airflow dags unpause $DAG >/dev/null 2>&1" || sin_conexion
    aws_en_airflow "airflow dags trigger --exec-date '$marca' --conf '{${conf}}' $DAG >/dev/null 2>&1" || sin_conexion
    for _ in $(seq 1 360); do
      estado="$(aws_en_airflow "airflow dags state $DAG '$marca' 2>/dev/null | tail -n 1 | cut -d, -f1 | tr -d '\r '")"
      case "$estado" in
        success) printf 'Corrida terminada: success\n'; exit 0 ;;
        failed) printf 'Corrida terminada: failed\n'; exit 1 ;;
      esac
      sleep 10
    done
    printf 'El DAG no terminó en 1 hora.\n' >&2
    exit 1
    ;;

  tareas)
    en_el_compadre "$COMPOSE exec -T postgres psql -U airflow -d airflow -c \"select task_id, state, try_number as intento, to_char(end_date, 'HH24:MI:SS') as termino from task_instance where dag_id = '$DAG' and run_id = (select run_id from dag_run where dag_id = '$DAG' order by start_date desc limit 1) order by start_date nulls last, task_id\"" || sin_conexion
    ;;

  log)
    tarea="${2:-}"
    [[ -n "$tarea" ]] || { printf 'Uso: compadre.sh log <tarea> [líneas]\n' >&2; exit 2; }
    aws_en_airflow "bash -c 'f=\$(ls -t /opt/airflow/logs/dag_id=$DAG/*/task_id=$tarea/attempt=*.log | head -1); grep -vE \"^\$|DeprecationWarning|warnings.warn\" \$f | tail -${3:-30} | cut -c1-300'" || sin_conexion
    ;;

  cli)
    shift
    argumentos=""
    for a in "$@"; do argumentos+=" '${a//\'/\'\\\'\'}'"; done
    aws_en_airflow "python -W ignore -m noticias.cli$argumentos" || exit 1
    ;;

  sql)
    shift
    [[ -n "${1:-}" ]] || { printf 'Uso: compadre.sh sql "<consulta>"\n' >&2; exit 2; }
    aws_en_airflow "python -W ignore -m noticias.cli sql '${1//\'/\'\\\'\'}'" || exit 1
    ;;

  programar)
    valor=0
    [[ "${2:-}" == on ]] && valor=1
    en_el_compadre "cd ~/lago && sed -i '/^DL_PROGRAMAR=/d' .env && echo DL_PROGRAMAR=$valor >> .env && docker compose -f docker/docker-compose.yml --project-directory . up -d >/dev/null 2>&1" || sin_conexion
    printf 'Ejecución horaria: %s\n' "$([[ $valor == 1 ]] && echo activada || echo desactivada)"
    ;;

  limpiar-airflow)
    aws_en_airflow "airflow dags delete $DAG --yes >/dev/null 2>&1" || sin_conexion
    for _ in $(seq 1 60); do
      aws_en_airflow "airflow dags list 2>/dev/null | grep -q $DAG" && break
      sleep 10
    done
    printf 'Historial de corridas borrado\n'
    ;;

  clave-airflow)
    en_el_compadre 'grep AIRFLOW_ADMIN_PASSWORD ~/lago/.secretos | cut -d= -f2' || sin_conexion
    ;;
esac
