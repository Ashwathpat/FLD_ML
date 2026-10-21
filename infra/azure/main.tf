terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  backend "azurerm" {
    # Populate via terraform init -backend-config=backend.hcl
    # resource_group_name  = "fld-screen-tfstate"
    # storage_account_name = "fldscreentfstate"
    # container_name       = "tfstate"
    # key                  = "azure/terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = "fld-screen-rg"
  location = var.location
  tags     = { project = "fld-screen" }
}

# ── Virtual Network ───────────────────────────────────────────────────────────
resource "azurerm_virtual_network" "vnet" {
  name                = "fld-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = { project = "fld-screen" }
}

resource "azurerm_subnet" "app" {
  name                 = "fld-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# ── Public IP ─────────────────────────────────────────────────────────────────
resource "azurerm_public_ip" "app" {
  name                = "fld-standby-pip"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = { project = "fld-screen" }
}

# ── NSG ───────────────────────────────────────────────────────────────────────
resource "azurerm_network_security_group" "app" {
  name                = "fld-nsg"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  security_rule {
    name                       = "HTTP"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
  security_rule {
    name                       = "HTTPS"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
  security_rule {
    name                       = "SSH"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.admin_cidr
    destination_address_prefix = "*"
  }
  tags = { project = "fld-screen" }
}

# ── NIC ───────────────────────────────────────────────────────────────────────
resource "azurerm_network_interface" "nic" {
  name                = "fld-nic"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.app.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }
  tags = { project = "fld-screen" }
}

resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.app.id
}

# ── VM ────────────────────────────────────────────────────────────────────────
resource "azurerm_linux_virtual_machine" "app" {
  name                = "fld-standby"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = "Standard_B1s"
  admin_username      = "deploy"
  custom_data         = filebase64("${path.module}/cloud-init.yaml")

  network_interface_ids = [azurerm_network_interface.nic.id]

  admin_ssh_key {
    username   = "deploy"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }
  tags = { project = "fld-screen" }
}

# ── Azure PostgreSQL Flexible Server ─────────────────────────────────────────
resource "azurerm_postgresql_flexible_server" "pg" {
  name                   = "fld-pg-standby-${var.suffix}"
  resource_group_name    = azurerm_resource_group.rg.name
  location               = azurerm_resource_group.rg.location
  version                = "16"
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  administrator_login    = var.db_user
  administrator_password = var.db_password
  tags                   = { project = "fld-screen" }
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "from_aws" {
  name             = "allow-aws-replicator"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = var.aws_elastic_ip
  end_ip_address   = var.aws_elastic_ip
}

# ── Blob Storage ──────────────────────────────────────────────────────────────
resource "azurerm_storage_account" "sa" {
  name                     = "fldscreen${var.suffix}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = { project = "fld-screen" }
}

resource "azurerm_storage_container" "images" {
  name                  = "images"
  storage_account_name  = azurerm_storage_account.sa.name
  container_access_type = "private"
}
