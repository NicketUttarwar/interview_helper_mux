data "aws_caller_identity" "current" {}

locals {
  merged_tags = merge(
    {
      Project     = var.project_name
      ManagedBy   = "terraform"
      Environment = var.environment
      App         = "interview_helper_mux"
    },
    var.common_tags,
  )

  # S3 bucket names cannot contain underscores.
  project_hyphenated = replace(var.project_name, "_", "-")
  account_suffix     = substr(data.aws_caller_identity.current.account_id, length(data.aws_caller_identity.current.account_id) - 6, 6)
  s3_bucket_name     = var.s3_bucket_name != "" ? var.s3_bucket_name : "${local.project_hyphenated}-rss-${local.account_suffix}"

  oac_name  = "${var.project_name}-oac"
  origin_id = "${var.project_name}-s3-origin"
}
