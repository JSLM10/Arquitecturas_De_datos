output "bucket" {
  value = aws_s3_bucket.lago.id
}

output "bucket_arn" {
  value = aws_s3_bucket.lago.arn
}
