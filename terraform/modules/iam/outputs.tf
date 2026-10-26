output "redshift_role_arn" {
  value = aws_iam_role.picotera_lee_la_bodega.arn
}

output "ec2_instance_profile" {
  value = aws_iam_instance_profile.compadre.name
}
