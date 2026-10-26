variable "region" {
  description = "Una sola region para todo el taller: Ohio."
  type        = string
  default     = "us-east-2"
}

variable "perfil" {
  description = "Perfil de AWS CLI con las credenciales de user_cli."
  type        = string
  default     = "user_cli"
}

variable "mi_ip_cidr" {
  description = "Mi IP publica con /32 (ej. 190.240.73.151/32). Es la unica que puede entrar por SSH, a Airflow y a Redshift."
  type        = string

  validation {
    condition     = can(cidrhost(var.mi_ip_cidr, 0)) && endswith(var.mi_ip_cidr, "/32")
    error_message = "Use una sola IP con /32, por ejemplo 190.240.73.151/32."
  }
}

variable "llave_publica" {
  description = "Ruta de la llave PUBLICA SSH (la privada nunca sale del PC)."
  type        = string
  default     = "~/.ssh/la-llave-dw.pub"
}

# ---------- Interruptores: se prende una pieza a la vez ----------
# La red, la bodega y los roles siempre se crean (no cuestan). Lo demas se prende cuando le toque.

variable "crear_ec2" {
  description = "true = crea el compadre (EC2 donde corren Airflow y dbt)."
  type        = bool
  default     = false
}

variable "crear_rds" {
  description = "true = crea el sancocho (RDS MySQL)."
  type        = bool
  default     = false
}

variable "crear_docdb" {
  description = "true = crea el bololo (DocumentDB)."
  type        = bool
  default     = false
}

variable "crear_redshift" {
  description = "true = crea la picotera (Redshift Serverless)."
  type        = bool
  default     = false
}

# ---------- Tamanos ----------

variable "clase_ec2" {
  description = "Tipo de la EC2. Airflow con Docker necesita unos 8 GB de RAM: t3.large."
  type        = string
  default     = "t3.large"
}

variable "clase_rds" {
  description = "Clase de la instancia RDS MySQL."
  type        = string
  default     = "db.t4g.micro"
}

variable "modo_docdb" {
  description = "serverless = DocumentDB Serverless (0.5 DCU minimo). aprovisionado = instancia fija."
  type        = string
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "aprovisionado"], var.modo_docdb)
    error_message = "modo_docdb debe ser 'serverless' o 'aprovisionado'."
  }
}

variable "clase_docdb" {
  description = "Clase usada solo si modo_docdb = aprovisionado."
  type        = string
  default     = "db.t4g.medium"
}

variable "redshift_rpu" {
  description = "RPU base de Redshift Serverless (minimo 4). Cobra por RPU-hora solo mientras corre consultas."
  type        = number
  default     = 4
}

variable "redshift_publico" {
  description = "true = la picotera se alcanza desde fuera de la VPC (hace falta para QuickSight y para el Query Editor desde el PC). Solo entran mi IP y QuickSight."
  type        = bool
  default     = true
}

variable "quicksight_cidr" {
  description = "Rango de IP desde el que QuickSight (Amazon Quick) se conecta a las bases en Ohio. Fuente: docs.aws.amazon.com/quicksight/latest/user/regions.html"
  type        = string
  default     = "52.15.247.160/27"
}
