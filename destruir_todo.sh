#!/usr/bin/env bash
# Borra lo que el taller dejo encendido en AWS y verifica que no quede nada cobrando.
#
#   bash destruir_todo.sh                    borra TODO (red, bodega, roles, EC2, RDS, DocumentDB y Redshift)
#   bash destruir_todo.sh --solo-lo-caro     apaga EC2, RDS, DocumentDB y Redshift; deja la red, la bodega y los roles
#
# Antes de borrar muestra cuantos recursos se van y pide confirmacion.
# Al final corre verificar_limpieza.sh (solo cuando se borra todo).

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF=(terraform -chdir="$RAIZ/terraform")
export AWS_PROFILE="${AWS_PROFILE:-user_cli}"

modo="todo"
case "${1:-}" in
  "") ;;
  --solo-lo-caro) modo="caro" ;;
  *)
    printf 'Uso: bash destruir_todo.sh [--solo-lo-caro]\n'
    exit 2
    ;;
esac

[[ -f "$RAIZ/terraform/terraform.tfvars" ]] || {
  printf 'Falta terraform/terraform.tfvars (copielo de terraform.tfvars.example, Punto 0 de la guia).\n'
  exit 1
}

"${TF[@]}" init -input=false >/dev/null || {
  printf 'terraform init fallo. Revise su conexion a Internet.\n'
  exit 1
}

if [[ -z "$("${TF[@]}" state list 2>/dev/null)" ]]; then
  printf '\nTerraform no tiene nada creado (el estado esta vacio), asi que no hay nada que borrar con el.\n'
  printf 'Reviso igual la cuenta por si quedo algo suelto:\n'
  bash "$RAIZ/verificar_limpieza.sh"
  exit $?
fi

if [[ "$modo" == "caro" ]]; then
  # Los -var le ganan a terraform.tfvars: apagan lo caro sin tocar el archivo.
  ARGS=(-var crear_ec2=false -var crear_rds=false -var crear_docdb=false -var crear_redshift=false)
  printf '\nSe van a APAGAR: EC2 (el compadre), RDS, DocumentDB y Redshift.\nSe quedan: la red, la bodega con sus datos y los roles.\n\n'
  "${TF[@]}" plan -input=false -no-color "${ARGS[@]}" | grep -E "will be destroyed|^Plan:|No changes" || true
else
  ARGS=()
  printf '\nSe va a BORRAR TODO lo del taller, incluida la bodega y los datos que tenga adentro.\n\n'
  "${TF[@]}" plan -destroy -input=false -no-color | grep -E "will be destroyed|^Plan:|No changes" || true
fi

printf '\n'
read -r -p "Escriba 'si' para continuar: " respuesta
[[ "$respuesta" == "si" ]] || {
  printf 'Cancelado. No se borro nada.\n'
  exit 0
}

if [[ "$modo" == "caro" ]]; then
  "${TF[@]}" apply -input=false -auto-approve "${ARGS[@]}" || {
    printf '\nNo termino bien. Lea el error de arriba, corrijalo y vuelva a correr este script: es seguro repetirlo.\n'
    exit 1
  }
  printf '\nListo: lo caro quedo apagado. Para volver a prenderlo, ponga los crear_* en true en terraform.tfvars y corra terraform apply.\n'
  exit 0
fi

# terraform destroy repite el plan completo (cientos de lineas). Se guarda todo en un log y en pantalla
# solo se ven el avance y los errores, para que la captura del Punto 10 quede legible.
LOG="$RAIZ/terraform/ultimo_destroy.log"
"${TF[@]}" destroy -input=false -auto-approve -no-color 2>&1 | tee "$LOG" |
  grep -E '^module\.[^ ]+: (Destroying|Destruction|Still destroying)|^Destroy complete|^Error|^[│╷╵]'
if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
  printf '\nNo termino bien. Lea el error de arriba (el detalle completo esta en %s) y vuelva a correr este script: es seguro repetirlo.\n' "$LOG"
  printf 'Si algo no se deja borrar, revise tambien la consola de AWS (RDS, DocumentDB, Redshift, EC2, VPC).\n'
  exit 1
fi

printf '\nTerraform termino de borrar. Verificando que no quede nada...\n'
bash "$RAIZ/verificar_limpieza.sh"
