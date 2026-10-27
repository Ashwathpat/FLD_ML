terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # backend "s3" {
  #   bucket         = "fld-screen-tfstate"
  #   key            = "aws/terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "fld-screen-tflock"
  # }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { project = "fld-screen" }
  }
}

# ── Data: latest Ubuntu 22.04 AMI ────────────────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# ── Key Pair ──────────────────────────────────────────────────────────────────
resource "aws_key_pair" "deploy" {
  key_name   = "fld-screen-deploy"
  public_key = var.ssh_public_key
}

# ── Security Group ────────────────────────────────────────────────────────────
resource "aws_security_group" "web" {
  name        = "fld-screen-web"
  description = "FLD-Screen web traffic"

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH (restricted)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "fld-screen-web" }
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────
resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.deploy.key_name
  vpc_security_group_ids = [aws_security_group.web.id]
  user_data              = file("${path.module}/cloud-init.yaml")
  tags                   = { Name = "fld-primary", project = "fld-screen" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "fld-primary-eip" }
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
resource "aws_db_instance" "pg" {
  identifier          = "fld-pg"
  engine              = "postgres"
  engine_version      = "16"
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  multi_az            = false
  publicly_accessible = false
  skip_final_snapshot = true
  username            = var.db_user
  password            = var.db_password
  tags                = { project = "fld-screen" }
}

# ── S3 Bucket ─────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "images" {
  bucket = "fld-screen-images-${var.suffix}"
  tags   = { project = "fld-screen" }
}

resource "aws_s3_bucket_versioning" "images" {
  bucket = aws_s3_bucket.images.id
  versioning_configuration { status = "Enabled" }
}

# ── SNS Alerting ──────────────────────────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "fld-screen-alerts"
  tags = { project = "fld-screen" }
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
