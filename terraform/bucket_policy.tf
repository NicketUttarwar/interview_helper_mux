data "aws_iam_policy_document" "origin_oac" {
  statement {
    sid    = "AllowCloudFrontOAC_${var.project_name}"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = [
      "s3:GetObject",
    ]

    resources = [
      "${aws_s3_bucket.origin.arn}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.podcast.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "origin" {
  bucket = aws_s3_bucket.origin.id
  policy = data.aws_iam_policy_document.origin_oac.json

  depends_on = [
    aws_s3_bucket_public_access_block.origin,
    aws_cloudfront_distribution.podcast,
  ]
}
