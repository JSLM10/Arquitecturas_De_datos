# Un solo bucket privado para todo el taller, con versionado para que ningun lote se sobrescriba en silencio.

data "aws_caller_identity" "yo" {}

resource "aws_s3_bucket" "bodega" {
  bucket        = "la-bodega-del-pelao-dw-${data.aws_caller_identity.yo.account_id}"
  force_destroy = true # permite borrar el bucket aunque tenga objetos (es un taller)

  tags = { Name = "la-bodega-del-pelao-dw" }
}

resource "aws_s3_bucket_public_access_block" "bodega" {
  bucket                  = aws_s3_bucket.bodega.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "bodega" {
  bucket = aws_s3_bucket.bodega.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bodega" {
  bucket = aws_s3_bucket.bodega.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
