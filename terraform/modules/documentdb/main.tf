# DocumentDB (reemplaza a MongoDB). Diferencias que importan: TLS obligatorio,
# retryWrites=false y sin operadores como $where o mapReduce.

locals {
  serverless = var.modo == "serverless"
}

resource "aws_security_group" "portero_bololo" {
  name        = "el-portero-del-bololo-dw"
  description = "Portero del bololo (DocumentDB): solo deja pasar al compadre por el 27017"
  vpc_id      = var.vpc_id

  tags = { Name = "el-portero-del-bololo-dw" }
}

resource "aws_vpc_security_group_ingress_rule" "docdb_desde_el_compadre" {
  security_group_id            = aws_security_group.portero_bololo.id
  description                  = "DocumentDB solo desde el compadre"
  ip_protocol                  = "tcp"
  from_port                    = 27017
  to_port                      = 27017
  referenced_security_group_id = var.sg_origen_id
}

resource "aws_docdb_subnet_group" "cocina" {
  name       = "la-cocina-del-bololo-dw"
  subnet_ids = var.subnet_ids

  tags = { Name = "la-cocina-del-bololo-dw" }
}

resource "aws_docdb_cluster" "bololo" {
  cluster_identifier = "el-bololo-dw"
  engine             = "docdb"
  engine_version     = "5.0.0" # la 5.0 es la que soporta Serverless

  master_username             = "pelao_admin"
  manage_master_user_password = true

  db_subnet_group_name   = aws_docdb_subnet_group.cocina.name
  vpc_security_group_ids = [aws_security_group.portero_bololo.id]

  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true

  dynamic "serverless_v2_scaling_configuration" {
    for_each = local.serverless ? [1] : []
    content {
      min_capacity = 0.5 # el minimo permitido
      max_capacity = 2
    }
  }

  tags = { Name = "el-bololo-dw" }
}

resource "aws_docdb_cluster_instance" "nodo" {
  identifier         = "el-bololo-dw-nodo-1"
  cluster_identifier = aws_docdb_cluster.bololo.id
  engine             = "docdb"
  instance_class     = local.serverless ? "db.serverless" : var.clase

  tags = { Name = "el-bololo-dw-nodo-1" }
}
