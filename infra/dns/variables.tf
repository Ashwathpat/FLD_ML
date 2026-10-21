variable "domain"        { description = "Registered domain name, e.g. fld-screen.example.com" }
variable "aws_ip"        { description = "AWS Elastic IP address" }
variable "azure_ip"      { description = "Azure VM static public IP address" }
variable "sns_topic_arn" { description = "SNS topic ARN for alarm notifications" }
