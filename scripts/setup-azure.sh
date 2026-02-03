#!/bin/bash
# One-time Azure resource setup for Agnirudra
# Run this once to create the resource group, storage account, service principal,
# PostgreSQL database, and Redis cache.
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
PG_SERVER="agnirudra-pg"
PG_ADMIN_USER="agni_admin"
PG_ADMIN_PASS="AgniPg$(openssl rand -hex 12)"
REDIS_NAME="agnirudra-redis"

echo "=== Agnirudra Azure Setup ==="
echo "Subscription: $SUBSCRIPTION_ID"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# 1. Create resource group
echo "[1/7] Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --subscription "$SUBSCRIPTION_ID"

# 2. Create storage account
echo "[2/7] Creating storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --subscription "$SUBSCRIPTION_ID"

# 3. Create blob container
echo "[3/7] Creating blob container..."
az storage container create \
  --name recordings \
  --account-name "$STORAGE_ACCOUNT" \
  --subscription "$SUBSCRIPTION_ID"

# 4. Create service principal
echo "[4/7] Creating service principal..."
echo ""
SP_OUTPUT=$(az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  --sdk-auth 2>/dev/null)
echo "$SP_OUTPUT"

# 5. Create PostgreSQL Flexible Server
echo ""
echo "[5/7] Creating PostgreSQL Flexible Server (this may take a few minutes)..."
az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN_USER" \
  --admin-password "$PG_ADMIN_PASS" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0 \
  --yes

echo "Creating databases..."
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name "tabtabtab-sheets"

az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name "tabtabtab-spreadjs-collab"

echo "Adding firewall rules..."
az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAll \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 255.255.255.255

# 6. Create Azure Cache for Redis
echo ""
echo "[6/7] Creating Azure Cache for Redis (this may take several minutes)..."
az redis create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REDIS_NAME" \
  --location "$LOCATION" \
  --sku Basic \
  --vm-size c0 \
  --redis-version 6 \
  --enable-non-ssl-port

echo "Retrieving Redis access key..."
REDIS_KEY=$(az redis list-keys \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REDIS_NAME" \
  --query primaryKey -o tsv)

# 7. Print summary
echo ""
echo "[7/7] Done!"
echo ""
echo "============================================================"
echo "  AGNIRUDRA AZURE SETUP COMPLETE"
echo "============================================================"
echo ""
echo "--- AZURE_CREDENTIALS (save as GitHub secret) ---"
echo "$SP_OUTPUT"
echo ""
echo "--- PostgreSQL ---"
echo "  Server:   ${PG_SERVER}.postgres.database.azure.com"
echo "  Admin:    $PG_ADMIN_USER"
echo "  Password: $PG_ADMIN_PASS"
echo "  Backend DB URL:"
echo "    postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASS}@${PG_SERVER}.postgres.database.azure.com:5432/tabtabtab-sheets?sslmode=require"
echo "  SpreadJS Collab DB URL:"
echo "    postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASS}@${PG_SERVER}.postgres.database.azure.com:5432/tabtabtab-spreadjs-collab?sslmode=require"
echo ""
echo "--- Redis ---"
echo "  Host: ${REDIS_NAME}.redis.cache.windows.net"
echo "  Key:  $REDIS_KEY"
echo "  URL:  redis://:${REDIS_KEY}@${REDIS_NAME}.redis.cache.windows.net:6379"
echo ""
echo "--- Next steps ---"
echo "  1. Run initial DB migrations (see plan Step 9)"
echo "  2. Run scripts/push-agni-secrets.sh in your app repo"
echo "  3. Commit and push, then open a claude/* PR to test"
