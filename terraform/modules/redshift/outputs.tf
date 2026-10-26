output "endpoint" {
  value = aws_redshiftserverless_workgroup.picotera.endpoint[0].address
}

output "secret_arn" {
  description = "ARN del secreto con la clave del administrador (la maneja Redshift)."
  value       = aws_redshiftserverless_namespace.picotera.admin_password_secret_arn
}

output "workgroup" {
  value = aws_redshiftserverless_workgroup.picotera.workgroup_name
}

output "base_de_datos" {
  value = local.db_name
}
