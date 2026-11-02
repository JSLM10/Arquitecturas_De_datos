# Un solo bucket para las tres zonas: bronze/, silver/ y gold/ (mas control/, cache_comprehend/ y athena-resultados/).

data "aws_caller_identity" "yo" {}

resource "aws_s3_bucket" "lago" {
  bucket        = "la-bodega-del-pelao-dl-${data.aws_caller_identity.yo.account_id}"
  force_destroy = true

  tags = { Name = "la-bodega-del-pelao-dl" }
}

resource "aws_s3_bucket_public_access_block" "lago" {
  bucket                  = aws_s3_bucket.lago.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "lago" {
  bucket = aws_s3_bucket.lago.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lago" {
  bucket = aws_s3_bucket.lago.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
