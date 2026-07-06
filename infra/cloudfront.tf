locals {
  ec2_origin_id = "ec2-app"
}

resource "aws_cloudfront_distribution" "app" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.app_name} — EC2 origin"
  price_class     = "PriceClass_100" # US + Europe only (cheapest)

  # ── Origin: EC2 nginx on port 80 ────────────────────────────────────────────
  origin {
    domain_name = aws_eip.app.public_dns
    origin_id   = local.ec2_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60 # CloudFront max without a quota increase; searches take ~6s
    }
  }

  # ── /search — POST endpoint, never cache ────────────────────────────────────
  ordered_cache_behavior {
    path_pattern     = "/search"
    target_origin_id = local.ec2_origin_id

    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies { forward = "all" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = false
  }

  # ── /agent* — SSE streaming agent search, never cache ───────────────────────
  ordered_cache_behavior {
    path_pattern     = "/agent*"
    target_origin_id = local.ec2_origin_id

    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies { forward = "all" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = false
  }

  # ── /experiments* — GET list + POST run, never cache ────────────────────────
  ordered_cache_behavior {
    path_pattern     = "/experiments*"
    target_origin_id = local.ec2_origin_id

    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies { forward = "all" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = false
  }

  # ── /health — no cache ──────────────────────────────────────────────────────
  ordered_cache_behavior {
    path_pattern     = "/health"
    target_origin_id = local.ec2_origin_id

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = false
  }

  # ── Default: static React assets — cache 24 h ───────────────────────────────
  default_cache_behavior {
    target_origin_id = local.ec2_origin_id

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 86400    # 1 day
    max_ttl                = 2592000  # 30 days
    compress               = true
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  # Free *.cloudfront.net TLS cert — no custom domain needed
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { App = var.app_name }
}
