output "bucket" {
  value = module.lago_s3.bucket
}

output "base_datos" {
  value = module.glue_athena.base_datos
}

output "workgroup_athena" {
  value = module.glue_athena.workgroup
}

output "ec2_ip_publica" {
  value = try(module.ec2_airflow[0].ip_publica, null)
}

output "ssh" {
  value = try("ssh -i ~/.ssh/la-llave-dw ec2-user@${module.ec2_airflow[0].ip_publica}", null)
}
