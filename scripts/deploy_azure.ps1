# scripts/deploy_azure.ps1
# Automates Azure Standby deployment for FLD-Screen

$ErrorActionPreference = "Stop"
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  FLD-Screen: Deploying Azure Standby Stack  " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Check Azure Login
Write-Host "`n[1/3] Checking Azure authentication..." -ForegroundColor Yellow
try {
    $account = az account show | ConvertFrom-Json
    Write-Host "  -> Logged in as: $($account.user.name)" -ForegroundColor Green
    Write-Host "  -> Subscription: $($account.name) ($($account.id))" -ForegroundColor Green
} catch {
    Write-Host "  -> Re-authenticating with Azure..." -ForegroundColor Yellow
    az login --tenant "29bebd42-f1ff-4c3d-9688-067e3460dc1f" --scope "https://graph.microsoft.com/.default"
}

# 2. Navigate and Apply Terraform
Write-Host "`n[2/3] Provisioning Azure Resources via Terraform..." -ForegroundColor Yellow
Set-Location -Path "$PSScriptRoot\..\infra\azure"
terraform apply -auto-approve

# 3. Output deployment details
Write-Host "`n[3/3] Deployment complete! Azure Outputs:" -ForegroundColor Green
terraform output
Write-Host "`nUse the output values in your .env configuration." -ForegroundColor Cyan
