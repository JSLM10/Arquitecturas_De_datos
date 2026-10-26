variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  description = "Redshift Serverless exige subredes en 3 zonas de disponibilidad distintas."
  type        = list(string)
}

variable "sg_origen_id" {
  description = "Portero del compadre."
  type        = string
}

variable "role_arn" {
  description = "Rol de IAM que deja a Redshift leer la bodega."
  type        = string
}

variable "rpu_base" {
  description = "RPU base (minimo 4)."
  type        = number
  default     = 4

  validation {
    condition     = var.rpu_base >= 4
    error_message = "El minimo de Redshift Serverless es 4 RPU."
  }
}

variable "publico" {
  description = "true = alcanzable desde fuera de la VPC (mi PC y QuickSight)."
  type        = bool
  default     = true
}

variable "mi_ip_cidr" {
  type = string
}

variable "quicksight_cidr" {
  type = string
}
