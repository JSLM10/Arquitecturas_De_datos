variable "cidr" {
  description = "Rango de direcciones de la VPC (el barrio)."
  type        = string
  default     = "10.70.0.0/16"
}

variable "mi_ip_cidr" {
  description = "Mi IP publica con /32: la unica que puede entrar por SSH y a Airflow."
  type        = string
}
