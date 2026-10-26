variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "sg_origen_id" {
  description = "Portero del compadre: el unico grupo que puede llegar a la base."
  type        = string
}

variable "modo" {
  description = "serverless o aprovisionado."
  type        = string
  default     = "serverless"
}

variable "clase" {
  description = "Clase usada solo si modo = aprovisionado."
  type        = string
  default     = "db.t4g.medium"
}
