resource "aws_s3_bucket" "origin" {
  bucket        = local.s3_bucket_name
  force_destroy = true

  tags = {
    Name = "${var.project_name}-rss"
  }

  # Allow bucket rename (new name first) so CloudFront can switch origins
  # without destroying the distribution / changing the public feed URL.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "origin" {
  bucket = aws_s3_bucket.origin.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "origin" {
  bucket = aws_s3_bucket.origin.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}
