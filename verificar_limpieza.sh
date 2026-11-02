#!/usr/bin/env bash
# Revisa que no quede nada del taller en la cuenta (us-east-2). Solo lee, no borra.
# Uso: bash verificar_limpieza.sh

set -uo pipefail

export AWS_PROFILE="${AWS_PROFILE:-user_cli}"
export AWS_DEFAULT_REGION="us-east-2"

quedan=0
sin_acceso=0

revisar() {
  local etiqueta="$1" salida
  shift
  if ! salida="$("$@" 2>/dev/null)"; then
    sin_acceso=$((sin_acceso + 1))
    printf '%s: sin acceso\n' "$etiqueta"
  elif [[ -z "${salida//[[:space:]]/}" || "$salida" == "None" ]]; then
    printf '%s: vacío\n' "$etiqueta"
  else
    quedan=$((quedan + 1))
    printf '%s: %s\n' "$etiqueta" "$(tr '\t\n' '  ' <<<"$salida")"
  fi
}

cuenta="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" || {
  printf 'No se pudo entrar a AWS con el perfil %s\n' "$AWS_PROFILE"
  exit 2
}
printf 'Cuenta %s · %s\n\n' "$cuenta" "$AWS_DEFAULT_REGION"

revisar "Instancias EC2" aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=el-compadre-dw" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query "Reservations[].Instances[].InstanceId" --output text
revisar "Volúmenes EBS" aws ec2 describe-volumes \
  --filters "Name=status,Values=available" --query "Volumes[].VolumeId" --output text
revisar "Llaves SSH" aws ec2 describe-key-pairs \
  --filters "Name=key-name,Values=la-llave-dw" --query "KeyPairs[].KeyName" --output text
revisar "IP elásticas" aws ec2 describe-addresses \
  --query "Addresses[?AssociationId==null].PublicIp" --output text
revisar "NAT gateways" aws ec2 describe-nat-gateways \
  --filter "Name=state,Values=pending,available" --query "NatGateways[].NatGatewayId" --output text
revisar "VPC" aws ec2 describe-vpcs \
  --filters "Name=tag:Name,Values=el-barrio-dw" --query "Vpcs[].VpcId" --output text
revisar "Instancias RDS" aws rds describe-db-instances \
  --query "DBInstances[?starts_with(DBInstanceIdentifier, 'el-sancocho')].DBInstanceIdentifier" --output text
revisar "Clústeres DocumentDB" aws docdb describe-db-clusters \
  --query "DBClusters[?starts_with(DBClusterIdentifier, 'el-bololo')].DBClusterIdentifier" --output text
revisar "Snapshots RDS/DocumentDB" aws rds describe-db-snapshots \
  --snapshot-type manual --query "DBSnapshots[].DBSnapshotIdentifier" --output text
revisar "Workgroups Redshift" aws redshift-serverless list-workgroups \
  --query "workgroups[?starts_with(workgroupName, 'la-picotera')].workgroupName" --output text
revisar "Namespaces Redshift" aws redshift-serverless list-namespaces \
  --query "namespaces[?starts_with(namespaceName, 'la-picotera')].namespaceName" --output text
revisar "Secretos" aws secretsmanager list-secrets \
  --query "SecretList[?starts_with(Name, 'rds!') || starts_with(Name, 'redshift!')].Name" --output text
revisar "Buckets S3" aws s3api list-buckets \
  --query "Buckets[?starts_with(Name, 'la-bodega-del-pelao-dw')].Name" --output text
revisar "Roles IAM" aws iam list-roles \
  --query "Roles[?starts_with(RoleName, 'la-picotera-') || starts_with(RoleName, 'el-compadre-')].RoleName" --output text
revisar "Perfiles IAM" aws iam list-instance-profiles \
  --query "InstanceProfiles[?starts_with(InstanceProfileName, 'el-compadre-')].InstanceProfileName" --output text

printf '\n'
if [[ $quedan -eq 0 && $sin_acceso -eq 0 ]]; then
  printf 'Todo limpio\n'
  exit 0
fi
[[ $quedan -gt 0 ]] && printf 'Queda algo en %d punto(s)\n' "$quedan"
[[ $sin_acceso -gt 0 ]] && printf 'No se pudo revisar %d punto(s)\n' "$sin_acceso"
exit 1
