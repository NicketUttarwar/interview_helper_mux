# Single region: S3 + CloudFront (OAC). ACM/custom domains are out of scope.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.merged_tags
  }
}
