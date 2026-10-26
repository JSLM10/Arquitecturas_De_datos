# Redshift Serverless (reemplaza a DuckDB). Entran por el 5439: el compadre y, si publico = true,
# mi IP y el rango de QuickSight de Ohio.

locals {
  db_name = "ecommerce_dw"
}

resource "aws_security_group" "portero_picotera" {
  name        = "el-portero-de-la-picotera-dw"
  description = "Portero de la picotera (Redshift): el compadre, mi PC y QuickSight"
  vpc_id      = var.vpc_id

  tags = { Name = "el-portero-de-la-picotera-dw" }
}

resource "aws_vpc_security_group_ingress_rule" "desde_el_compadre" {
  security_group_id            = aws_security_group.portero_picotera.id
  description                  = "Redshift desde el compadre (Airflow y dbt)"
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
  referenced_security_group_id = var.sg_origen_id
}

resource "aws_vpc_security_group_ingress_rule" "desde_mi_pc" {
  count = var.publico ? 1 : 0

  security_group_id = aws_security_group.portero_picotera.id
  description       = "Redshift desde mi PC"
  ip_protocol       = "tcp"
  from_port         = 5439
  to_port           = 5439
  cidr_ipv4         = var.mi_ip_cidr
}

resource "aws_vpc_security_group_ingress_rule" "desde_quicksight" {
  count = var.publico ? 1 : 0

  security_group_id = aws_security_group.portero_picotera.id
  description       = "Redshift desde QuickSight (Ohio)"
  ip_protocol       = "tcp"
  from_port         = 5439
  to_port           = 5439
  cidr_ipv4         = var.quicksight_cidr
}

resource "aws_vpc_security_group_egress_rule" "salida_libre" {
  security_group_id = aws_security_group.portero_picotera.id
  description       = "Salida libre (hacia S3 para el COPY)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_redshiftserverless_namespace" "picotera" {
  namespace_name = "la-picotera-dw"
  db_name        = local.db_name
  admin_username = "pelao_admin"

  # La clave la crea y la guarda Redshift en Secrets Manager. Terraform nunca la ve.
  manage_admin_password = true

  iam_roles            = [var.role_arn]
  default_iam_role_arn = var.role_arn

  tags = { Name = "la-picotera-dw" }
}

resource "aws_redshiftserverless_workgroup" "picotera" {
  namespace_name = aws_redshiftserverless_namespace.picotera.namespace_name
  workgroup_name = "la-picotera-dw-wg"

  base_capacity       = var.rpu_base
  publicly_accessible = var.publico

  subnet_ids         = var.subnet_ids
  security_group_ids = [aws_security_group.portero_picotera.id]

  tags = { Name = "la-picotera-dw-wg" }
}
