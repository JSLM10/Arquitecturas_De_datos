# RDS MySQL (reemplaza al MySQL local). La clave la genera y guarda RDS en Secrets Manager.

resource "aws_security_group" "portero_sancocho" {
  name        = "el-portero-del-sancocho-dw"
  description = "Portero del sancocho (RDS MySQL): solo deja pasar al compadre por el 3306"
  vpc_id      = var.vpc_id

  tags = { Name = "el-portero-del-sancocho-dw" }
}

resource "aws_vpc_security_group_ingress_rule" "mysql_desde_el_compadre" {
  security_group_id            = aws_security_group.portero_sancocho.id
  description                  = "MySQL solo desde el compadre"
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  referenced_security_group_id = var.sg_origen_id
}

resource "aws_db_subnet_group" "cocina" {
  name       = "la-cocina-del-sancocho-dw"
  subnet_ids = var.subnet_ids

  tags = { Name = "la-cocina-del-sancocho-dw" }
}

resource "aws_db_instance" "sancocho" {
  identifier        = "el-sancocho-dw"
  engine            = "mysql"
  engine_version    = "8.4"
  instance_class    = var.clase
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "ecommerce"
  username = "pelao_admin"

  # La contrasena la genera y la guarda RDS en AWS Secrets Manager.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.cocina.name
  vpc_security_group_ids = [aws_security_group.portero_sancocho.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period      = 0    # sin backups automaticos: es un taller
  skip_final_snapshot          = true # al borrar, no deja snapshots facturables
  delete_automated_backups     = true
  deletion_protection          = false
  apply_immediately            = true
  performance_insights_enabled = false

  tags = { Name = "el-sancocho-dw" }
}
