#!/usr/bin/env bash
# Lleva el codigo al compadre y levanta Airflow con Docker Compose. Se puede repetir.
# Uso: bash scripts/aws/desplegar_compadre.sh

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LLAVE="${LLAVE_SSH:-$HOME/.ssh/la-llave-dw}"
SSH_OPCIONES=(-i "$LLAVE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

salida() {
  local valor
  valor="$(terraform -chdir="$RAIZ/terraform" output -no-color -raw "$1" 2>/dev/null)" || valor=""
  if [[ -z "$valor" || "$valor" == "null" || "$valor" =~ [[:space:]] ]]; then
    printf 'Falta el output "%s" de Terraform. Prenda ese servicio (crear_* = true) y corra terraform apply.\n' "$1" >&2
    exit 1
  fi
  printf '%s' "$valor"
}

ip="$(salida ec2_ip_publica)"
[[ -f "$LLAVE" ]] || { printf 'No encuentro la llave %s (paso 0.3 de la guia).\n' "$LLAVE" >&2; exit 1; }

TEMPORAL="$(mktemp -d)"
trap 'rm -rf "$TEMPORAL"' EXIT

cat > "$TEMPORAL/publico.env" <<EOF
AWS_REGION=us-east-2
AIRFLOW_UID=1000
DW_BUCKET=$(salida bucket)
RDS_ENDPOINT=$(salida rds_endpoint)
RDS_SECRET_ARN=$(salida rds_secret_arn)
DOCDB_ENDPOINT=$(salida docdb_endpoint)
DOCDB_SECRET_ARN=$(salida docdb_secret_arn)
REDSHIFT_ENDPOINT=$(salida redshift_endpoint)
REDSHIFT_SECRET_ARN=$(salida redshift_secret_arn)
REDSHIFT_DB=$(salida redshift_base_de_datos)
REDSHIFT_ROLE_ARN=$(salida redshift_role_arn)
EOF

printf 'Empaquetando el codigo...\n'
tar czf "$TEMPORAL/codigo.tgz" -C "$RAIZ" \
  --exclude='__pycache__' --exclude='src/dbt/target' --exclude='src/dbt/logs' --exclude='src/dbt/dbt_packages' \
  --exclude='src/dbt_redshift/target' --exclude='src/dbt_redshift/logs' --exclude='src/dbt_redshift/dbt_packages' \
  docker src

printf 'Copiando al compadre (%s)...\n' "$ip"
scp "${SSH_OPCIONES[@]}" -q "$TEMPORAL/codigo.tgz" "$TEMPORAL/publico.env" "ec2-user@$ip:~/" || {
  printf 'No pude conectar. Revise que su IP no haya cambiado (guia: errores comunes).\n' >&2
  exit 1
}

printf 'Armando y levantando Airflow en el compadre (la primera vez tarda unos minutos)...\n'
ssh "${SSH_OPCIONES[@]}" "ec2-user@$ip" 'bash -s' <<'REMOTO'
set -euo pipefail
mkdir -p ~/dw
tar xzf ~/codigo.tgz -C ~/dw
cd ~/dw

# Claves de Airflow: se generan una vez y se quedan en la EC2 (permisos 600).
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
cat ~/publico.env .secretos > .env
chmod 600 .env .secretos

docker compose -f docker/docker-compose.aws.yml --project-directory . up -d --build

printf 'Esperando a que Airflow responda'
for _ in $(seq 1 60); do
  if curl -fs http://localhost:8080/health >/dev/null 2>&1; then printf ' listo.\n'; break; fi
  printf '.'; sleep 5
done

printf 'Esperando a que Airflow registre el DAG'
for _ in $(seq 1 40); do
  if docker compose -f docker/docker-compose.aws.yml --project-directory . exec -T airflow-scheduler \
       airflow dags list 2>/dev/null | grep -q ecommerce_dw_aws; then printf ' listo.\n'; break; fi
  printf '.'; sleep 5
done
docker compose -f docker/docker-compose.aws.yml --project-directory . exec -T airflow-scheduler \
  airflow dags unpause ecommerce_dw_aws >/dev/null 2>&1 || true
REMOTO

printf '\nListo. Airflow: http://%s:8080  (usuario: airflow)\n' "$ip"
printf 'La clave de Airflow se ve con:  bash scripts/aws/compadre.sh clave-airflow\n'
