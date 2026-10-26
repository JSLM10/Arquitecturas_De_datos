terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Terraform se autentica como user_cli (perfil de ~/.aws/credentials). NUNCA con la cuenta raiz.
provider "aws" {
  region  = var.region
  profile = var.perfil

  default_tags {
    tags = {
      Proyecto = "taller-datawarehouse-eia"
      Manejado = "terraform"
    }
  }
}
