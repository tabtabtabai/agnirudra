#!/bin/bash
# One-time Azure resource setup for Agnirudra
# Run this once to create the resource group, storage account, and service principal.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - A subscription with credits available
#
# Usage:
#   ./scripts/setup-azure.sh <subscription-id>

set -euo pipefail

SUBSCRIPTION_ID="${1:?Usage: $0 <subscription-id>}"
RESOURCE_GROUP="agnirudra-rg"
LOCATION="eastus"
STORAGE_ACCOUNT="agnirudrarecordings"
SP_NAME="agnirudra-gh-actions"

echo "=== Agnirudra Azure Setup ==="
echo "Subscription: $SUBSCRIPTION_ID"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# 1. Create resource group
echo "[1/4] Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --subscription "$SUBSCRIPTION_ID"

# 2. Create storage account
echo "[2/4] Creating storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --subscription "$SUBSCRIPTION_ID"

# 3. Create blob container
echo "[3/4] Creating blob container..."
az storage container create \
  --name recordings \
  --account-name "$STORAGE_ACCOUNT" \
  --subscription "$SUBSCRIPTION_ID"

# 4. Create service principal
echo "[4/4] Creating service principal..."
echo "Save the following JSON as the AZURE_CREDENTIALS GitHub secret:"
echo ""
az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  --sdk-auth

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy the JSON output above"
echo "  2. Go to your GitHub repo -> Settings -> Secrets -> Actions"
echo "  3. Create a secret named AZURE_CREDENTIALS with the JSON value"
echo "  4. Also add ANTHROPIC_API_KEY secret with your Anthropic key"
