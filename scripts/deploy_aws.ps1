# scripts/deploy_aws.ps1
# Automates AWS Primary deployment for FLD-Screen

$ErrorActionPreference = "Stop"
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  FLD-Screen: Deploying AWS Primary Stack    " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Check AWS Credentials
Write-Host "`n[1/3] Checking AWS Credentials..." -ForegroundColor Yellow
if (-not $env:AWS_ACCESS_KEY_ID -and -not (Test-Path "$HOME\.aws\credentials")) {
    Write-Host "  [!] AWS Credentials not found in environment or ~/.aws/credentials" -ForegroundColor Red
    Write-Host "  Please enter your AWS Access Key ID:"
    $env:AWS_ACCESS_KEY_ID = Read-Host
    Write-Host "  Please enter your AWS Secret Access Key:"
    $env:AWS_SECRET_ACCESS_KEY = Read-Host -AsSecureString | [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($_))
    Write-Host "  Please enter your AWS Region (default: us-east-1):"
    $reg = Read-Host
    $env:AWS_DEFAULT_REGION = if ($reg) { $reg } else { "us-east-1" }
}

# 2. Navigate and Apply Terraform
Write-Host "`n[2/3] Provisioning AWS Resources via Terraform..." -ForegroundColor Yellow
Set-Location -Path "$PSScriptRoot\..\infra\aws"
terraform apply -auto-approve

# 3. Output deployment details
Write-Host "`n[3/3] Deployment complete! AWS Outputs:" -ForegroundColor Green
terraform output
Write-Host "`nUse the output values in your .env configuration." -ForegroundColor Cyan
