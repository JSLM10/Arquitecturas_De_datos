#!/usr/bin/env bash
# Atajos para trabajar con el compadre (la EC2). Lee la IP y los endpoints de los outputs de Terraform,
# asi no hay que copiar ni pegar nada a mano.
#
#   bash scripts/aws/compadre.sh estado                       esta listo el compadre? versiones de Docker
#   bash scripts/aws/compadre.sh entrar                       abre una sesion SSH
#   bash scripts/aws/compadre.sh copiar <archivo>             copia un archivo al compadre (queda en ~)
#   bash scripts/aws/compadre.sh probar rds|docdb|redshift    prueba la conexion a esa base
#   bash scripts/aws/compadre.sh desplegar                    lleva el codigo y levanta Airflow
#   bash scripts/aws/compadre.sh fuentes <script> [opciones]  generate_data | append_batch | simulate_changes
#   bash scripts/aws/compadre.sh pipeline [modo] [lote] [fallo]  dispara el DAG y espera (modo: auto/completo/incremental)
#   bash scripts/aws/compadre.sh sql "<consulta>"             consulta Redshift
#   bash scripts/aws/compadre.sh tareas                       estado de cada tarea del DAG
#   bash scripts/aws/compadre.sh log <tarea> [lineas]         ultimo log de una tarea (ej. dbt_test)
#   bash scripts/aws/compadre.sh limpiar-airflow              borra el historial de corridas del DAG
#   bash scripts/aws/compadre.sh usuario-quicksight           crea el usuario de solo lectura de QuickSight
#   bash scripts/aws/compadre.sh clave-airflow                muestra la clave de Airflow (cuidado al capturar)

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LLAVE="${LLAVE_SSH:-$HOME/.ssh/la-llave-dw}"
SSH_OPCIONES=(-i "$LLAVE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
COMPOSE='cd ~/dw && docker compose -f docker/docker-compose.aws.yml --project-directory .'

# Devuelve el valor de un output de Terraform, o falla si no existe (recurso apagado o sin crear).
salida_tf() {
  local valor
  valor="$(terraform -chdir="$RAIZ/terraform" output -no-color -raw "$1" 2>/dev/null)" || return 1
  [[ "$valor" =~ ^[^[:space:]]+$ && "$valor" != "null" ]] || return 1
  printf '%s' "$valor"
}

case "${1:-}" in
  estado | entrar | copiar | probar | desplegar | fuentes | pipeline | sql | tareas | log | limpiar-airflow | usuario-quicksight | clave-airflow) ;;
  *)
    sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac

if [[ "$1" == "desplegar" ]]; then
  exec bash "$RAIZ/scripts/aws/desplegar_compadre.sh"
fi

ip="$(salida_tf ec2_ip_publica)" || ip=""
if [[ -z "$ip" ]]; then
  printf 'El compadre no esta prendido. Ponga crear_ec2 = true en terraform/terraform.tfvars y corra terraform apply.\n' >&2
  exit 1
fi
[[ -f "$LLAVE" ]] || {
  printf 'No encuentro la llave %s. Cree la llave con el paso 0.3 de la guia.\n' "$LLAVE" >&2
  exit 1
}

en_el_compadre() {
  ssh "${SSH_OPCIONES[@]}" "ec2-user@$ip" "$@"
}

ayuda_ssh() {
  printf '\nNo pude conectar al compadre (%s). Causas comunes:\n' "$ip" >&2
  printf '  - Su IP cambio: corra  curl -s https://checkip.amazonaws.com  , actualice mi_ip_cidr en terraform.tfvars y haga terraform apply.\n' >&2
  printf '  - El compadre apenas esta arrancando: espere un minuto y repita.\n' >&2
  printf '  - Aviso de "host key changed": corra  ssh-keygen -R %s  y repita.\n' "$ip" >&2
  exit 1
}

copiar() {
  scp "${SSH_OPCIONES[@]}" "$1" "ec2-user@$ip:~" || ayuda_ssh
}

case "$1" in
  estado)
    en_el_compadre 'if [ -f /var/lib/cloud/instance/compadre-listo ]; then echo "El compadre esta LISTO."; else echo "El compadre todavia se esta armando; repita en un minuto."; fi
docker --version
docker compose version' || ayuda_ssh
    ;;

  entrar)
    en_el_compadre || ayuda_ssh
    ;;

  copiar)
    [[ -n "${2:-}" ]] || {
      printf 'Uso: bash scripts/aws/compadre.sh copiar <archivo>\n' >&2
      exit 2
    }
    copiar "$2"
    printf 'Copiado a ec2-user@%s:~\n' "$ip"
    ;;

  probar)
    servicio="${2:-}"
    copiar "$RAIZ/scripts/aws/probar_conexiones.py"
    en_el_compadre 'pip3 install --user -q boto3 pymysql pymongo' || ayuda_ssh

    case "$servicio" in
      rds)
        endpoint="$(salida_tf rds_endpoint)"
        secreto="$(salida_tf rds_secret_arn)"
        [[ -n "$endpoint" ]] || { printf 'RDS no esta prendido (crear_rds = true).\n' >&2; exit 1; }
        en_el_compadre "python3 -W ignore probar_conexiones.py rds --endpoint '$endpoint' --secreto '$secreto'"
        ;;
      docdb)
        endpoint="$(salida_tf docdb_endpoint)"
        secreto="$(salida_tf docdb_secret_arn)"
        [[ -n "$endpoint" ]] || { printf 'DocumentDB no esta prendido (crear_docdb = true).\n' >&2; exit 1; }
        en_el_compadre "[ -f global-bundle.pem ] || curl -sfO https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
python3 -W ignore probar_conexiones.py docdb --endpoint '$endpoint' --secreto '$secreto' --cert global-bundle.pem"
        ;;
      redshift)
        workgroup="$(salida_tf redshift_workgroup)"
        secreto="$(salida_tf redshift_secret_arn)"
        base="$(salida_tf redshift_base_de_datos)"
        [[ -n "$secreto" ]] || { printf 'Redshift no esta prendido (crear_redshift = true).\n' >&2; exit 1; }
        en_el_compadre "python3 -W ignore probar_conexiones.py redshift --workgroup '$workgroup' --secreto '$secreto' --base '$base'"
        ;;
      *)
        printf 'Uso: bash scripts/aws/compadre.sh probar rds|docdb|redshift\n' >&2
        exit 2
        ;;
    esac
    ;;

  fuentes)
    shift
    [[ -n "${1:-}" ]] || { printf 'Uso: bash scripts/aws/compadre.sh fuentes generate_data|append_batch|simulate_changes [opciones]\n' >&2; exit 2; }
    en_el_compadre "$COMPOSE exec -T -e PYTHONWARNINGS=ignore airflow-scheduler python -W ignore -m ecommerce_dw.aws.lanzador $*" || ayuda_ssh
    ;;

  pipeline)
    modo="${2:-auto}"
    lote="${3:-}"
    fallo="${4:-}"
    marca="$(date -u +'%Y-%m-%dT%H:%M:%S+00:00')"
    conf="{\"modo\": \"$modo\", \"reprocesar_lote\": \"$lote\", \"simular_fallo\": \"$fallo\"}"
    printf 'Disparando ecommerce_dw_aws (modo=%s, reprocesar_lote=%s, simular_fallo=%s)...\n' "$modo" "${lote:-ninguno}" "${fallo:-no}"
    # Un DAG en pausa deja la corrida en cola para siempre: se despausa siempre antes de disparar.
    en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags unpause ecommerce_dw_aws >/dev/null 2>&1" || ayuda_ssh
    en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags trigger --exec-date '$marca' --conf '$conf' ecommerce_dw_aws >/dev/null 2>&1" || ayuda_ssh
    for _ in $(seq 1 360); do
      estado="$(en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags state ecommerce_dw_aws '$marca' 2>/dev/null | tail -n 1 | cut -d, -f1 | tr -d '\r '")"
      case "$estado" in
        success) printf 'ecommerce_dw_aws termino en SUCCESS.\n'; exit 0 ;;
        failed) printf 'ecommerce_dw_aws termino en FAILED. Mire el log de la tarea que fallo en Airflow.\n' >&2; exit 1 ;;
      esac
      sleep 10
    done
    printf 'El DAG no termino en 1 hora; revise Airflow.\n' >&2
    exit 1
    ;;

  sql)
    shift
    [[ -n "${1:-}" ]] || { printf 'Uso: bash scripts/aws/compadre.sh sql "select ..."\n' >&2; exit 2; }
    consulta="${1//\'/\'\\\'\'}"
    en_el_compadre "$COMPOSE exec -T airflow-scheduler python -W ignore -m ecommerce_dw.aws.consulta '$consulta'" || ayuda_ssh
    ;;

  tareas)
    en_el_compadre "$COMPOSE exec -T postgres psql -U airflow -d airflow -c \"select task_id, state, try_number as intento, to_char(end_date, 'HH24:MI:SS') as termino from task_instance where dag_id = 'ecommerce_dw_aws' order by start_date nulls last, task_id\"" || ayuda_ssh
    ;;

  log)
    tarea="${2:-}"
    [[ -n "$tarea" ]] || { printf 'Uso: bash scripts/aws/compadre.sh log <tarea> [lineas]
' >&2; exit 2; }
    en_el_compadre "$COMPOSE exec -T airflow-scheduler bash -c 'f=\$(ls -t /opt/airflow/logs/dag_id=ecommerce_dw_aws/*/task_id=$tarea/attempt=*.log | head -1); echo \$f; grep -vE \"^\$|DeprecationWarning|warnings.warn\" \$f | tail -${3:-30} | cut -c1-300'" || ayuda_ssh
    ;;

  limpiar-airflow)
    # Borra las corridas viejas del DAG (las de depuracion) y espera a que Airflow lo vuelva a registrar.
    en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags delete ecommerce_dw_aws --yes >/dev/null 2>&1" || ayuda_ssh
    printf 'Historial borrado. Esperando a que Airflow vuelva a registrar el DAG'
    for _ in $(seq 1 60); do
      if en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags list 2>/dev/null | grep -q ecommerce_dw_aws"; then
        en_el_compadre "$COMPOSE exec -T airflow-scheduler airflow dags unpause ecommerce_dw_aws >/dev/null 2>&1"
        printf ' listo.
'; exit 0
      fi
      printf '.'; sleep 10
    done
    printf '
Airflow no registro el DAG en 10 minutos; revise los logs del scheduler.
' >&2
    exit 1
    ;;

  usuario-quicksight)
    read -r -s -p "Clave para quicksight_lector (letras y numeros, minimo 8, con mayuscula, minuscula y numero): " clave
    printf '\n'
    [[ "$clave" =~ ^[A-Za-z0-9]{8,64}$ && "$clave" =~ [A-Z] && "$clave" =~ [a-z] && "$clave" =~ [0-9] ]] || {
      printf 'La clave no cumple el formato.\n' >&2
      exit 2
    }
    consulta() { en_el_compadre "$COMPOSE exec -T airflow-scheduler python -W ignore -m ecommerce_dw.aws.consulta \"$1\"" ; }
    consulta "create user quicksight_lector password '$clave'" >/dev/null 2>&1 \
      || consulta "alter user quicksight_lector password '$clave'" >/dev/null || ayuda_ssh
    consulta "grant usage on schema marts to quicksight_lector" >/dev/null || ayuda_ssh
    consulta "grant select on all tables in schema marts to quicksight_lector" >/dev/null || ayuda_ssh
    consulta "alter default privileges in schema marts grant select on tables to quicksight_lector" >/dev/null || ayuda_ssh
    printf 'Usuario quicksight_lector listo: solo lectura sobre marts.\n'
    ;;

  clave-airflow)
    en_el_compadre 'grep AIRFLOW_ADMIN_PASSWORD ~/dw/.secretos | cut -d= -f2' || ayuda_ssh
    ;;
esac
