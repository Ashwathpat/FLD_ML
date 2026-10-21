variable "aws_region"      { default = "ap-south-1" }
variable "ssh_public_key"  { description = "SSH public key for EC2 access" }
variable "admin_cidr"      { default = "0.0.0.0/0" }
variable "db_user"         { default = "fld_user" }
variable "db_password"     { sensitive = true }
variable "suffix"          { description = "Unique suffix for globally-unique resource names" }
variable "alert_email"     { description = "Email for CloudWatch SNS alerts" }

output "ec2_public_ip"    { value = aws_eip.app.public_ip }
output "rds_endpoint"     { value = aws_db_instance.pg.endpoint }
output "s3_bucket_name"   { value = aws_s3_bucket.images.bucket }
