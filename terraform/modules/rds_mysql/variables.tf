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

variable "clase" {
  type    = string
  default = "db.t4g.micro"
}
