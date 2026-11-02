variable "region" {
  type    = string
  default = "us-east-2"
}

variable "perfil" {
  description = "Perfil de AWS CLI con las credenciales de user_cli."
  type        = string
  default     = "user_cli"
}

variable "mi_ip_cidr" {
  description = "Mi IP publica con /32: la unica que entra por SSH y a Airflow."
  type        = string

  validation {
    condition     = can(cidrhost(var.mi_ip_cidr, 0)) && endswith(var.mi_ip_cidr, "/32")
    error_message = "Use una sola IP con /32, por ejemplo 203.0.113.10/32."
  }
}

variable "llave_publica" {
  description = "Ruta de la llave publica SSH."
  type        = string
  default     = "~/.ssh/la-llave-dw.pub"
}

variable "crear_ec2" {
  description = "true = crea el compadre (EC2 con Airflow). El bucket, los roles y Glue/Athena se crean siempre."
  type        = bool
  default     = false
}

variable "clase_ec2" {
  type    = string
  default = "t3.large"
}
