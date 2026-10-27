terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # backend "s3" {
  #   key = "dns/terraform.tfstate"
  # }
}

provider "aws" {
  region = "us-east-1" # Route 53 health-check metrics must be in us-east-1
  default_tags {
    tags = { project = "fld-screen" }
  }
}

# ── Route 53 Hosted Zone ──────────────────────────────────────────────────────
data "aws_route53_zone" "main" {
  name = var.domain
}

# ── Health Check on AWS primary ───────────────────────────────────────────────
resource "aws_route53_health_check" "primary" {
  fqdn              = "aws.${var.domain}"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/readyz"
  request_interval  = 10
  failure_threshold = 3
  tags              = { Name = "fld-primary-hc" }
}

# ── DNS Records: Failover ─────────────────────────────────────────────────────
resource "aws_route53_record" "primary" {
  zone_id        = data.aws_route53_zone.main.zone_id
  name           = "app.${var.domain}"
  type           = "A"
  set_identifier = "primary"
  health_check_id = aws_route53_health_check.primary.id

  failover_routing_policy {
    type = "PRIMARY"
  }

  records = [var.aws_ip]
  ttl     = 30
}

resource "aws_route53_record" "secondary" {
  zone_id        = data.aws_route53_zone.main.zone_id
  name           = "app.${var.domain}"
  type           = "A"
  set_identifier = "secondary"

  failover_routing_policy {
    type = "SECONDARY"
  }

  records = [var.azure_ip]
  ttl     = 30
}

# Direct hostnames for CI smoke tests
resource "aws_route53_record" "aws_direct" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "aws.${var.domain}"
  type    = "A"
  records = [var.aws_ip]
  ttl     = 60
}

resource "aws_route53_record" "azure_direct" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "az.${var.domain}"
  type    = "A"
  records = [var.azure_ip]
  ttl     = 60
}

# ── CloudWatch Alarm → SNS Email on primary failure ────────────────────────────
resource "aws_cloudwatch_metric_alarm" "failover" {
  alarm_name          = "fld-primary-down"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HealthCheckStatus"
  namespace           = "AWS/Route53"
  period              = 60
  statistic           = "Minimum"
  threshold           = 1
  alarm_description   = "FLD-Screen primary (AWS) is failing health checks"
  alarm_actions       = [var.sns_topic_arn]
  dimensions          = { HealthCheckId = aws_route53_health_check.primary.id }
}
