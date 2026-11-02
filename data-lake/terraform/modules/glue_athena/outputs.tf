output "base_datos" {
  value = aws_glue_catalog_database.periodico.name
}

output "workgroup" {
  value = aws_athena_workgroup.pregunton.name
}
