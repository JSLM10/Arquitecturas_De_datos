output "bucket" {
  description = "La bodega del pelao (S3)."
  value       = module.bodega_s3.bucket
}

output "vpc_id" {
  value = module.red.vpc_id
}

output "ec2_ip_publica" {
  description = "IP publica del compadre (para SSH y para Airflow en el puerto 8080)."
  value       = try(module.ec2_airflow[0].ip_publica, null)
}

output "ssh" {
  description = "Comando para entrar al compadre."
  value       = try("ssh -i ~/.ssh/la-llave-dw ec2-user@${module.ec2_airflow[0].ip_publica}", null)
}

output "rds_endpoint" {
  value = try(module.rds_mysql[0].endpoint, null)
}

output "rds_secret_arn" {
  description = "ARN del secreto con la clave de RDS (la clave vive en Secrets Manager, no en Terraform)."
  value       = try(module.rds_mysql[0].secret_arn, null)
}

output "docdb_endpoint" {
  value = try(module.documentdb[0].endpoint, null)
}

output "docdb_secret_arn" {
  value = try(module.documentdb[0].secret_arn, null)
}

output "redshift_endpoint" {
  value = try(module.redshift[0].endpoint, null)
}

output "redshift_secret_arn" {
  value = try(module.redshift[0].secret_arn, null)
}

output "redshift_workgroup" {
  value = try(module.redshift[0].workgroup, null)
}

output "redshift_base_de_datos" {
  value = try(module.redshift[0].base_de_datos, null)
}

output "redshift_role_arn" {
  description = "Rol que permite a Redshift leer la bodega (se usa en el COPY)."
  value       = module.iam.redshift_role_arn
}
