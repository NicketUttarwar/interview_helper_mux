output "aws_region" {
  description = "Region used by this stack (also written to secrets as AWS_DEFAULT_REGION)."
  value       = var.aws_region
}

output "s3_bucket_id" {
  description = "Private origin bucket name (PODCAST_S3_BUCKET)."
  value       = aws_s3_bucket.origin.id
}

output "s3_bucket_arn" {
  description = "Origin bucket ARN."
  value       = aws_s3_bucket.origin.arn
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (PODCAST_CLOUDFRONT_DISTRIBUTION_ID)."
  value       = aws_cloudfront_distribution.podcast.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain (e.g. dxxxx.cloudfront.net)."
  value       = aws_cloudfront_distribution.podcast.domain_name
}

output "feed_base_url" {
  description = "HTTPS base URL for the feed and media (PODCAST_FEED_BASE_URL)."
  value       = "https://${aws_cloudfront_distribution.podcast.domain_name}"
}

output "feed_url" {
  description = "Full RSS feed URL to submit to Apple / Spotify."
  value       = "https://${aws_cloudfront_distribution.podcast.domain_name}/feed.xml"
}

output "project_name" {
  description = "Project tag / logical name base."
  value       = var.project_name
}

output "oac_id" {
  description = "CloudFront Origin Access Control ID."
  value       = aws_cloudfront_origin_access_control.origin.id
}
