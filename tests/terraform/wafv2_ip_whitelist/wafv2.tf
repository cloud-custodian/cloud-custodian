resource "aws_wafv2_ip_set" "unallowed_addresses" {
  name               = "unallowed-addresses"
  ip_address_version = "IPV4"
  addresses          = ["192.168.0.0/16"]
  scope              = "REGIONAL"
}

resource "aws_wafv2_web_acl_association" "unallowed_addresses" {
  resource_arn = aws_lb.alb_waf_v2_ip_whitelisting_unallowed_addresses.arn
  web_acl_arn  = aws_wafv2_web_acl.ip_whitelisting_unallowed_addresses.arn
}

resource "aws_wafv2_web_acl" "ip_whitelisting_unallowed_addresses" {
  name  = "unallowed-addresses"
  scope = "REGIONAL"

  default_action {
    block {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = false
    metric_name                = "foo"
    sampled_requests_enabled   = false
  }

  rule {
    name     = "foo"
    priority = 1

    visibility_config {
      cloudwatch_metrics_enabled = false
      metric_name                = "foo"
      sampled_requests_enabled   = false
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.unallowed_addresses.arn
      }
    }

    action {
      allow {}
    }
  }
}

resource "aws_wafv2_ip_set" "allowed_addresses_only" {
  name               = "allowed-addresses-only"
  ip_address_version = "IPV4"
  addresses          = ["192.168.0.0/28"]
  scope              = "REGIONAL"
}

resource "aws_wafv2_web_acl_association" "allowed_addresses_only" {
  resource_arn = aws_lb.alb_waf_v2_ip_whitelisting_allowed_addresses_only.arn
  web_acl_arn  = aws_wafv2_web_acl.ip_whitelisting_allowed_addresses_only.arn
}

resource "aws_wafv2_web_acl" "ip_whitelisting_allowed_addresses_only" {
  name  = "allowed-addresses-only"
  scope = "REGIONAL"

  default_action {
    block {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = false
    metric_name                = "foo"
    sampled_requests_enabled   = false
  }

  rule {
    name     = "foo"
    priority = 1

    visibility_config {
      cloudwatch_metrics_enabled = false
      metric_name                = "foo"
      sampled_requests_enabled   = false
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.allowed_addresses_only.arn
      }
    }

    action {
      allow {}
    }
  }
}
