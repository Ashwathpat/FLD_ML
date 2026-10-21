variable "location"        { default = "eastus" }
variable "ssh_public_key"  { description = "SSH public key for VM access" }
variable "admin_cidr"      { default = "0.0.0.0/0" }
variable "db_user"         { default = "fld_user" }
variable "db_password"     { sensitive = true }
variable "suffix"          { description = "Unique suffix (e.g. team initials + 4 digit number)" }
variable "aws_elastic_ip"  { description = "AWS Elastic IP to allow-list in Azure DB firewall" }

output "vm_public_ip"      { value = azurerm_public_ip.app.ip_address }
output "pg_fqdn"           { value = azurerm_postgresql_flexible_server.pg.fqdn }
output "storage_account"   { value = azurerm_storage_account.sa.name }
