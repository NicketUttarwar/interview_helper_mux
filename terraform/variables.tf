variable "aws_region" {
  type        = string
  description = "AWS region for S3 and related resources. Must be us-east-1 for this stack."
  default     = "us-east-1"

  validation {
    condition     = var.aws_region == "us-east-1"
    error_message = "This stack is single-region: aws_region must be us-east-1."
  }
}

variable "project_name" {
  type        = string
  description = "Logical base name (underscores OK). Used in tags, OAC name, CloudFront comment. S3 bucket uses hyphenated form."
  default     = "the_war_room_001"
}

variable "show_title" {
  type        = string
  description = "Human show title used in the CloudFront distribution comment."
  default     = "The War Room"
}

variable "environment" {
  type        = string
  description = "Environment label for tags (e.g. prod)."
  default     = "prod"
}

variable "s3_bucket_name" {
  type        = string
  description = "Optional override for the origin bucket. Empty = {hyphenated-project}-rss-{account_last6}."
  default     = ""
}

variable "common_tags" {
  type        = map(string)
  description = "Extra tags merged onto all taggable resources."
  default     = {}
}

variable "cloudfront_price_class" {
  type        = string
  description = "CloudFront price class for the distribution."
  default     = "PriceClass_100"
}
