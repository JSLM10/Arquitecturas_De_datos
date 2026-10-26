# Un solo Terraform, un modulo por servicio.
# red, bodega_s3 e iam se crean siempre; el resto se prende con los interruptores crear_*.

module "red" {
  source = "./modules/red"

  mi_ip_cidr = var.mi_ip_cidr
}

module "bodega_s3" {
  source = "./modules/bodega_s3"
}

module "iam" {
  source = "./modules/iam"

  bucket_arn = module.bodega_s3.bucket_arn
}

module "ec2_airflow" {
  count  = var.crear_ec2 ? 1 : 0
  source = "./modules/ec2_airflow"

  subnet_id         = module.red.subnet_ids[0]
  security_group_id = module.red.sg_compadre_id
  instance_profile  = module.iam.ec2_instance_profile
  clase             = var.clase_ec2
  llave_publica     = var.llave_publica
}

module "rds_mysql" {
  count  = var.crear_rds ? 1 : 0
  source = "./modules/rds_mysql"

  vpc_id       = module.red.vpc_id
  subnet_ids   = module.red.subnet_ids
  sg_origen_id = module.red.sg_compadre_id
  clase        = var.clase_rds
}

module "documentdb" {
  count  = var.crear_docdb ? 1 : 0
  source = "./modules/documentdb"

  vpc_id       = module.red.vpc_id
  subnet_ids   = module.red.subnet_ids
  sg_origen_id = module.red.sg_compadre_id
  modo         = var.modo_docdb
  clase        = var.clase_docdb
}

module "redshift" {
  count  = var.crear_redshift ? 1 : 0
  source = "./modules/redshift"

  vpc_id          = module.red.vpc_id
  subnet_ids      = module.red.subnet_ids
  sg_origen_id    = module.red.sg_compadre_id
  role_arn        = module.iam.redshift_role_arn
  rpu_base        = var.redshift_rpu
  publico         = var.redshift_publico
  mi_ip_cidr      = var.mi_ip_cidr
  quicksight_cidr = var.quicksight_cidr
}
