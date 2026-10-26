# Roles: la-picotera-lee-la-bodega (Redshift lee la bodega) y el-compadre-airflow-rol (permisos de la EC2).

data "aws_region" "actual" {}
data "aws_caller_identity" "yo" {}

# ---------- Rol de Redshift ----------
data "aws_iam_policy_document" "confianza_redshift" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "picotera_lee_la_bodega" {
  name               = "la-picotera-lee-la-bodega"
  assume_role_policy = data.aws_iam_policy_document.confianza_redshift.json
}

resource "aws_iam_role_policy" "solo_leer_la_bodega" {
  name = "solo-leer-la-bodega"
  role = aws_iam_role.picotera_lee_la_bodega.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:GetBucketLocation", "s3:ListBucket"]
      Resource = [var.bucket_arn, "${var.bucket_arn}/*"]
    }]
  })
}

# ---------- Rol del compadre (EC2) ----------
data "aws_iam_policy_document" "confianza_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "compadre_airflow" {
  name               = "el-compadre-airflow-rol"
  assume_role_policy = data.aws_iam_policy_document.confianza_ec2.json
}

resource "aws_iam_role_policy" "lo_que_hace_el_compadre" {
  name = "lo-que-hace-el-compadre"
  role = aws_iam_role.compadre_airflow.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "LeerYEscribirEnLaBodega"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetBucketLocation"]
        Resource = [var.bucket_arn, "${var.bucket_arn}/*"]
      },
      {
        Sid    = "LeerLasClavesQueGuardaAWS"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = [
          "arn:aws:secretsmanager:${data.aws_region.actual.region}:${data.aws_caller_identity.yo.account_id}:secret:rds!*",
          "arn:aws:secretsmanager:${data.aws_region.actual.region}:${data.aws_caller_identity.yo.account_id}:secret:redshift!*"
        ]
      },
      {
        Sid    = "ConsultarRedshiftPorLaDataAPI"
        Effect = "Allow"
        Action = [
          "redshift-data:ExecuteStatement",
          "redshift-data:BatchExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult",
          "redshift-data:CancelStatement",
          "redshift-data:ListStatements"
        ]
        Resource = "*"
      },
      {
        Sid      = "VerLaPicotera"
        Effect   = "Allow"
        Action   = ["redshift-serverless:GetWorkgroup", "redshift-serverless:GetNamespace", "redshift-serverless:ListWorkgroups"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "compadre" {
  name = "el-compadre-airflow-perfil"
  role = aws_iam_role.compadre_airflow.name
}
