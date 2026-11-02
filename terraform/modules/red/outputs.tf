output "vpc_id" {
  value = aws_vpc.barrio.id
}

output "subnet_ids" {
  value = aws_subnet.esquina[*].id
}

output "sg_compadre_id" {
  description = "Portero del compadre. Las bases de datos solo dejan pasar a este grupo."
  value       = aws_security_group.portero_compadre.id
}
