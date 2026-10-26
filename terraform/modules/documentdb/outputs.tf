output "endpoint" {
  value = aws_docdb_cluster.bololo.endpoint
}

output "secret_arn" {
  value = aws_docdb_cluster.bololo.master_user_secret[0].secret_arn
}
