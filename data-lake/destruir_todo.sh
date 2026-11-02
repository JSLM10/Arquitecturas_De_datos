#!/usr/bin/env bash
# Borra lo que el data lake dejó en AWS y verifica que no quede nada cobrando.
#
#   bash data-lake/destruir_todo.sh                 borra TODO (red, bodega, Glue, Athena, roles y EC2)
#   bash data-lake/destruir_todo.sh --solo-la-ec2   apaga solo la EC2; deja la red, la bodega, Glue y Athena

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF=(terraform -chdir="$RAIZ/terraform")
export AWS_PROFILE="${AWS_PROFILE:-user_cli}"

modo="todo"
case "${1:-}" in
  "") ;;
  --solo-la-ec2) modo="ec2" ;;
  *)
    printf 'Uso: bash data-lake/destruir_todo.sh [--solo-la-ec2]\n'
    exit 2
    ;;
esac

[[ -f "$RAIZ/terraform/terraform.tfvars" ]] || {
  printf 'Falta data-lake/terraform/terraform.tfvars (copie terraform.tfvars.example y ponga su IP).\n'
  exit 1
}

"${TF[@]}" init -input=false >/dev/null || {
  printf 'terraform init falló. Revise su conexión a Internet.\n'
  exit 1
}

if [[ -z "$("${TF[@]}" state list 2>/dev/null)" ]]; then
  printf '\nTerraform no tiene nada creado. Reviso igual la cuenta por si quedó algo suelto:\n\n'
  bash "$RAIZ/verificar_limpieza.sh"
  exit $?
fi

if [[ "$modo" == "ec2" ]]; then
  ARGS=(-var crear_ec2=false)
  printf '\nSe va a APAGAR la EC2. Se quedan la red, la bodega con sus datos, Glue, Athena y los roles.\n\n'
  "${TF[@]}" plan -input=false -no-color "${ARGS[@]}" | grep -E "will be destroyed|^Plan:|No changes" || true
else
  ARGS=()
  printf '\nSe va a BORRAR TODO el data lake, incluida la bodega y los datos que tenga adentro.\n\n'
  "${TF[@]}" plan -destroy -input=false -no-color | grep -E "will be destroyed|^Plan:|No changes" || true
fi

printf '\n'
read -r -p "Escriba 'si' para continuar: " respuesta
[[ "$respuesta" == "si" ]] || {
  printf 'Cancelado. No se borró nada.\n'
  exit 0
}

if [[ "$modo" == "ec2" ]]; then
  "${TF[@]}" apply -input=false -auto-approve "${ARGS[@]}" || exit 1
  printf '\nLa EC2 quedó apagada. Para volver a prenderla: crear_ec2 = true y terraform apply.\n'
  exit 0
fi

LOG="$RAIZ/terraform/ultimo_destroy.log"
"${TF[@]}" destroy -input=false -auto-approve -no-color 2>&1 | tee "$LOG" |
  grep -E '^module\.[^ ]+: (Destroying|Destruction|Still destroying)|^Destroy complete|^Error|^[│╷╵]'
if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
  printf '\nNo terminó bien (detalle en %s). Vuelva a correr este script: es seguro repetirlo.\n' "$LOG"
  exit 1
fi

printf '\nVerificando que no quede nada...\n\n'
bash "$RAIZ/verificar_limpieza.sh"
