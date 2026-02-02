# Azure Deployment Script for Legacy Documentation
# Usage: .\deploy_to_azure.ps1

# --- CONFIGURATION (UPDATE THESE) ---
$RESOURCE_GROUP = "rg-ipn-projects"
$ACR_NAME = "myregistry"            # Your Azure Container Registry Name
$APP_NAME = "legacy-docs-app"       # Name of the Container App
$LOCATION = "westeurope"            # automated-choice
$IMAGE_TAG = "v1"

# --- 1. Login to Azure (if needed) ---
Write-Host "Checking Azure Login..."
az account show
if ($LASTEXITCODE -ne 0) {
    Write-Host "Please login to Azure..."
    az login
}

# --- 2. Build and Push Image ---
Write-Host "Building Docker Image..."
$FULL_IMAGE_NAME = "$ACR_NAME.azurecr.io/legacy-docs:$IMAGE_TAG"

# Login to ACR
az acr login --name $ACR_NAME

# Build (using standard docker command)
docker build -t $FULL_IMAGE_NAME .

# Push
Write-Host "Pushing Image to ACR..."
docker push $FULL_IMAGE_NAME

# --- 3. Deploy/Update Container App ---
Write-Host "Deploying Container App..."

# Check if app exists to decide between create or update
az containerapp show --name $APP_NAME --resource-group $RESOURCE_GROUP
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating new Container App..."
    az containerapp create `
      --name $APP_NAME `
      --resource-group $RESOURCE_GROUP `
      --image $FULL_IMAGE_NAME `
      --target-port 80 `
      --ingress external `
      --env-vars "GENERATE_ON_START=true" `
      --query properties.configuration.ingress.fqdn
} else {
    Write-Host "Updating existing Container App..."
    az containerapp update `
      --name $APP_NAME `
      --resource-group $RESOURCE_GROUP `
      --image $FULL_IMAGE_NAME
}

Write-Host "Deployment Complete!"
Write-Host "Don't forget to set your secrets (GITHUB_TOKEN, ANTHROPIC_API_KEY) in the Azure Portal or using 'az containerapp secret set'"
