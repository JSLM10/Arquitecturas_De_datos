# La red del taller. Las bases no tienen IP publica: solo dejan pasar al grupo de seguridad del compadre.

data "aws_region" "actual" {}

data "aws_availability_zones" "disponibles" {
  state = "available"
}

locals {
  letras = ["a", "b", "c"]
}

resource "aws_vpc" "barrio" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "el-barrio-dw" }
}

resource "aws_subnet" "esquina" {
  count = 3

  vpc_id                  = aws_vpc.barrio.id
  cidr_block              = cidrsubnet(var.cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.disponibles.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "la-esquina-${local.letras[count.index]}-dw" }
}

resource "aws_internet_gateway" "puerta_al_mar" {
  vpc_id = aws_vpc.barrio.id
  tags   = { Name = "la-puerta-al-mar-dw" }
}

resource "aws_route_table" "calle_principal" {
  vpc_id = aws_vpc.barrio.id
  tags   = { Name = "la-calle-principal-dw" }
}

resource "aws_route" "salida_al_mar" {
  route_table_id         = aws_route_table.calle_principal.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.puerta_al_mar.id
}

resource "aws_route_table_association" "esquina" {
  count = 3

  subnet_id      = aws_subnet.esquina[count.index].id
  route_table_id = aws_route_table.calle_principal.id
}

resource "aws_vpc_endpoint" "trocha_a_la_bodega" {
  vpc_id            = aws_vpc.barrio.id
  service_name      = "com.amazonaws.${data.aws_region.actual.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.calle_principal.id]

  tags = { Name = "la-trocha-a-la-bodega-dw" }
}

# ---------- El portero del compadre (EC2 con Airflow y dbt) ----------
resource "aws_security_group" "portero_compadre" {
  name        = "el-portero-del-compadre-dw"
  description = "Portero del compadre (EC2): SSH y Airflow solo desde mi PC"
  vpc_id      = aws_vpc.barrio.id

  tags = { Name = "el-portero-del-compadre-dw" }
}

resource "aws_vpc_security_group_ingress_rule" "ssh_desde_mi_pc" {
  security_group_id = aws_security_group.portero_compadre.id
  description       = "SSH desde mi PC"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.mi_ip_cidr
}

resource "aws_vpc_security_group_ingress_rule" "airflow_desde_mi_pc" {
  security_group_id = aws_security_group.portero_compadre.id
  description       = "Interfaz de Airflow desde mi PC"
  ip_protocol       = "tcp"
  from_port         = 8080
  to_port           = 8080
  cidr_ipv4         = var.mi_ip_cidr
}

resource "aws_vpc_security_group_egress_rule" "compadre_sale_libre" {
  security_group_id = aws_security_group.portero_compadre.id
  description       = "El compadre sale a donde quiera (Docker Hub, GitHub, PyPI, AWS)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
