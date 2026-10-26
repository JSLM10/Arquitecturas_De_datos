output "bucket" {
  value = aws_s3_bucket.bodega.id
}

output "bucket_arn" {
  value = aws_s3_bucket.bodega.arn
}
