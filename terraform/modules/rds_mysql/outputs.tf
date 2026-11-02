output "endpoint" {
  value = aws_db_instance.sancocho.address
}

output "secret_arn" {
  description = "ARN del secreto (la clave vive en Secrets Manager, no en Terraform)."
  value       = aws_db_instance.sancocho.master_user_secret[0].secret_arn
}
