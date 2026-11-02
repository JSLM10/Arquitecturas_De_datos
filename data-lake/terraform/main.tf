# Data Lake de noticias. Reutiliza por referencia los modulos de red y EC2 del Data Warehouse
# (terraform/modules, sin modificarlos); el resto de modulos es propio.
# Solo debe estar desplegado un taller a la vez: comparten nombres de red, llave y EC2.

module "red" {
  source = "../../terraform/modules/red"

  mi_ip_cidr = var.mi_ip_cidr
}

module "lago_s3" {
  source = "./modules/lago_s3"
}

module "glue_athena" {
  source = "./modules/glue_athena"

  bucket = module.lago_s3.bucket
}

module "lago_iam" {
  source = "./modules/lago_iam"

  bucket_arn = module.lago_s3.bucket_arn
  base_datos = module.glue_athena.base_datos
}

module "ec2_airflow" {
  count  = var.crear_ec2 ? 1 : 0
  source = "../../terraform/modules/ec2_airflow"

  subnet_id         = module.red.subnet_ids[0]
  security_group_id = module.red.sg_compadre_id
  instance_profile  = module.lago_iam.perfil
  clase             = var.clase_ec2
  llave_publica     = var.llave_publica
}
