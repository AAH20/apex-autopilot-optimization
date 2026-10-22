# AWS — always-free services only.
# Lambda (1M req/mo), DynamoDB (25 GB + 25 WCU/RCU), S3 (5 GB),
# API Gateway HTTP (1M calls/mo), CloudFront (1 TB out/mo),
# CloudWatch Logs (5 GB), Budgets tripwire.

resource "aws_lambda_function" "api" {
  function_name = "mcft-api"
  runtime       = "python3.12"
  role          = "arn:aws:iam::000000000000:role/mcft-lambda-role"
  handler       = "index.handler"
  filename      = "lambda.zip"
  source_code_hash = filebase64sha256("lambda.zip")

  timeout = 3
  memory_size = 128

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.app_state.name
      BUCKET     = aws_s3_bucket.assets.id
    }
  }
}

resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_api_gatewayv2_api" "api" {
  name          = "mcft-api"
  protocol_type = "HTTP"
  target        = aws_lambda_function.api.arn
}

resource "aws_api_gatewayv2_stage" "api" {
  api_id      = aws_api_gatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_dynamodb_table" "app_state" {
  name             = "mcft-app-state"
  billing_mode     = "PROVISIONED"
  read_capacity    = 25
  write_capacity   = 25
  hash_key         = "pk"
  range_key        = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  # Always-free: 25 GB storage, 25 WCU/RCU. Point-in-time recovery OFF to stay free.
  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_s3_bucket" "assets" {
  bucket = "mcft-assets"
  acl    = "private"

  ownership_controls {
    rule {
      object_ownership = "BucketOwnerEnforced"
    }
  }
}

resource "aws_cloudfront_distribution" "edge" {
  origin {
    domain_name = aws_s3_bucket.assets.bucket_regional_domain_name
    origin_id   = "S3-mcft-assets"

    s3_origin_config {
      origin_access_identity = ""  # legacy; OAI replaced by OAC, kept minimal for validate
    }
  }

  enabled             = false
  is_ipv6_enabled     = false
  comment             = "MCFT edge — CloudFront always-free (1 TB out/mo)"
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-mcft-assets"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "allow-all"
    min_ttl                = 0
    default_ttl            = 86400
    max_ttl                = 86400
  }

  price_class = "PriceClass_All"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/mcft-api"
  retention_in_days = 7
}

# Budgets tripwire: alerts when projected cost exceeds $0.50 (any real spend).
resource "aws_budgets_budget" "tripwire" {
  name             = "mcft-aws-tripwire"
  budget_type      = "COST"
  limit_amount     = 0.50
  limit_unit       = "USD"
  time_unit        = "MONTHLY"

  notification {
    comparison_operator = "GREATER_THAN"
    threshold           = 80
    threshold_type      = "PERCENTAGE"
    notification_type   = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
