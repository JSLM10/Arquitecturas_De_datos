variable "subnet_id" {
  description = "Esquina (subred publica) donde vive el compadre."
  type        = string
}

variable "security_group_id" {
  description = "Portero del compadre."
  type        = string
}

variable "instance_profile" {
  description = "Perfil de IAM con los permisos del compadre."
  type        = string
}

variable "clase" {
  description = "Tipo de EC2."
  type        = string
  default     = "t3.large"
}

variable "llave_publica" {
  description = "Ruta de la llave publica SSH."
  type        = string
}

variable "disco_gb" {
  description = "Tamano del disco. Las imagenes de Docker de Airflow pesan varios GB."
  type        = number
  default     = 30
}
