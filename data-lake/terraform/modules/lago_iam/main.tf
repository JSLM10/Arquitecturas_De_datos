# Rol de la EC2: bucket del lago, Comprehend, Glue (solo su base) y Athena.

data "aws_region" "actual" {}
data "aws_caller_identity" "yo" {}

data "aws_iam_policy_document" "confianza_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

locals {
  glue = "arn:aws:glue:${data.aws_region.actual.region}:${data.aws_caller_identity.yo.account_id}"
}

resource "aws_iam_role" "compadre" {
  name               = "el-compadre-lago-rol"
  assume_role_policy = data.aws_iam_policy_document.confianza_ec2.json
}

resource "aws_iam_role_policy" "lo_que_hace_el_compadre" {
  name = "lo-que-hace-el-compadre-lago"
  role = aws_iam_role.compadre.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "LeerYEscribirEnElLago"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:AbortMultipartUpload", "s3:ListBucketMultipartUploads"]
        Resource = [var.bucket_arn, "${var.bucket_arn}/*"]
      },
      {
        Sid    = "EnriquecerConComprehend"
        Effect = "Allow"
        Action = [
          "comprehend:DetectDominantLanguage",
          "comprehend:BatchDetectDominantLanguage",
          "comprehend:DetectEntities",
          "comprehend:BatchDetectEntities",
          "comprehend:DetectKeyPhrases",
          "comprehend:BatchDetectKeyPhrases"
        ]
        Resource = "*"
      },
      {
        Sid    = "CatalogoDeGlue"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase", "glue:GetDatabases",
          "glue:GetTable", "glue:GetTables",
          "glue:GetPartition", "glue:GetPartitions",
          "glue:BatchGetPartition", "glue:CreatePartition", "glue:BatchCreatePartition",
          "glue:UpdatePartition", "glue:BatchUpdatePartition", "glue:DeletePartition", "glue:BatchDeletePartition"
        ]
        Resource = [
          "${local.glue}:catalog",
          "${local.glue}:database/${var.base_datos}",
          "${local.glue}:table/${var.base_datos}/*"
        ]
      },
      {
        Sid    = "ConsultarConAthena"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution", "athena:StopQueryExecution",
          "athena:GetQueryExecution", "athena:GetQueryResults",
          "athena:GetWorkGroup", "athena:ListQueryExecutions"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "compadre" {
  name = "el-compadre-lago-perfil"
  role = aws_iam_role.compadre.name
}
