# Azure Infrastructure Setup Script for Documentation Viewer
# Usage: .\setup_infra.ps1 -SubscriptionId "YOUR_SUBSCRIPTION_ID"

param (
    [string]$SubscriptionId,
    [string]$Location = "westeurope",
    [string]$ResourceGroupName = "udp-docs-rg",
    [string]$AcrName = "udpdocsacr$((Get-Random -Minimum 1000 -Maximum 9999))", # Randomize to ensure uniqueness
    [string]$AppServicePlanName = "udp-docs-plan",
    [string]$WebAppName = "udp-docs-app-$((Get-Random -Minimum 1000 -Maximum 9999))" # Randomize to ensure uniqueness
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host "`n=================================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "=================================================`n"
}

function Write-Success {
    param([string]$Message)
    Write-Host " [OK] $Message" -ForegroundColor Green
}

# 1. Check Azure CLI
Write-Header "Checking Prerequisites"
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI (az) is not installed. Please install it first."
    exit 1
}
Write-Success "Azure CLI found."

# 2. Login Check
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Success "Logged in as $($account.user.name)"
} catch {
    Write-Warning "Not logged in. Opening login window..."
    az login
}

# 3. Set Subscription
if ($SubscriptionId) {
    az account set --subscription $SubscriptionId
    Write-Success "Set subscription to $SubscriptionId"
}

# 4. Create Resource Group
Write-Header "Creating Infrastructure"
Write-Host "Creating Resource Group: $ResourceGroupName..."
az group create --name $ResourceGroupName --location $Location --output none
Write-Success "Resource Group created."

# 5. Create ACR
Write-Host "Creating Container Registry: $AcrName..."
$acrExists = az acr check-name --name $AcrName --query nameAvailable --output tsv
if ($acrExists -eq "false") {
    Write-Warning "ACR $AcrName already exists, using existing."
} else {
    az acr create --resource-group $ResourceGroupName --name $AcrName --sku Basic --admin-enabled true --output none
    Write-Success "ACR created."
}

# 6. Create App Service Plan
Write-Host "Creating App Service Plan: $AppServicePlanName (Linux)..."
az appservice plan create --name $AppServicePlanName --resource-group $ResourceGroupName --sku B1 --is-linux --output none
Write-Success "App Service Plan created."

# 7. Create Web App
Write-Host "Creating Web App: $WebAppName..."
az webapp create --resource-group $ResourceGroupName --plan $AppServicePlanName --name $WebAppName --deployment-container-image-name "nginx" --output none
Write-Success "Web App created."

# 8. Configure Identity & Permissions
Write-Header "Configuring Security"

# Enable System Identity
Write-Host "Enabling Managed Identity for Web App..."
az webapp identity assign --name $WebAppName --resource-group $ResourceGroupName --output none
$spId = az webapp show --name $WebAppName --resource-group $ResourceGroupName --query identity.principalId --output tsv

# Get ACR ID
$acrId = az acr show --name $AcrName --resource-group $ResourceGroupName --query id --output tsv

# Assign Role
Write-Host "Granting Web App permission to pull from ACR..."
az role assignment create --assignee $spId --scope $acrId --role AcrPull --output none
Write-Success "Permissions granted."

# 9. Generate GitHub Secrets
Write-Header "Generating Deployment Credentials"
Write-Host "Creating Service Principal for GitHub Actions..."
$spName = "github-actions-docs-$WebAppName"
$creds = az ad sp create-for-rbac --name $spName --role contributor --scopes /subscriptions/$(az account show --query id --output tsv)/resourceGroups/$ResourceGroupName --sdk-auth --output json

Write-Header "SETUP COMPLETE!"
Write-Host "Please configure the following Secrets in your GitHub Repository:" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------"
Write-Host "Secret Name: AZURE_CREDENTIALS" -ForegroundColor White
Write-Host "Value:" -ForegroundColor Gray
Write-Host $creds
Write-Host "-------------------------------------------------------------"
Write-Host "Secret Name: ACR_NAME" -ForegroundColor White
Write-Host "Value: $AcrName.azurecr.io" -ForegroundColor Green
Write-Host "-------------------------------------------------------------"
Write-Host "Secret Name: APP_SERVICE_NAME" -ForegroundColor White
Write-Host "Value: $WebAppName" -ForegroundColor Green
Write-Host "-------------------------------------------------------------"

Write-Host "`nNote: Don't forget to update your .github/workflows/deploy.yml with these new resource names!" -ForegroundColor Yellow
