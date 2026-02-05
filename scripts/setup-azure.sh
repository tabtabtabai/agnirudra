#!/bin/bash
# One-time Azure resource setup for Agnirudra
# Run this once to create the resource group, storage account, service principal,
# PostgreSQL database, and Redis cache.
#
# Safe to re-run — skips resources that already exist.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - A subscription with credits available
#
# Usage:
#   ./scripts/setup-azure.sh <subscription-id> [location]

set -euo pipefail

SUBSCRIPTION_ID="${1:?Usage: $0 <subscription-id> [location]}"
LOCATION="${2:-eastus}"
RESOURCE_GROUP="agnirudra-rg"
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
if az group show --name "$RESOURCE_GROUP" --subscription "$SUBSCRIPTION_ID" &>/dev/null; then
  echo "[1/7] Resource group already exists, skipping."
else
  echo "[1/7] Creating resource group..."
  az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --subscription "$SUBSCRIPTION_ID"
fi

# 2. Create storage account
if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --subscription "$SUBSCRIPTION_ID" &>/dev/null; then
  echo "[2/7] Storage account already exists, skipping."
else
  echo "[2/7] Creating storage account..."
  az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --subscription "$SUBSCRIPTION_ID"
fi

# 3. Create blob container
echo "[3/7] Ensuring blob container exists..."
az storage container create \
  --name recordings \
  --account-name "$STORAGE_ACCOUNT" \
  --subscription "$SUBSCRIPTION_ID" 2>/dev/null || true

# 4. Create service principal
if az ad sp list --display-name "$SP_NAME" --query "[0].appId" -o tsv 2>/dev/null | grep -q .; then
  echo "[4/7] Service principal already exists. Resetting credentials..."
  SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "$SP_NAME" \
    --role Contributor \
    --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
    --sdk-auth 2>/dev/null)
else
  echo "[4/7] Creating service principal..."
  SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "$SP_NAME" \
    --role Contributor \
    --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
    --sdk-auth 2>/dev/null)
fi
echo "$SP_OUTPUT"

# 5. Create PostgreSQL Flexible Server
if az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$PG_SERVER" &>/dev/null; then
  echo "[5/7] PostgreSQL server already exists, skipping."
  # Still need the password — prompt for it
  echo "  NOTE: Reusing existing server. If you forgot the password, reset it in Azure Portal."
  PG_ADMIN_PASS="(existing — see Azure Portal)"
else
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
fi

# Create example database (customize for your app)
echo "Creating example database..."
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name "agnirudra-app" 2>/dev/null || true

# NOTE: Add your own databases here if needed:
# az postgres flexible-server db create \
#   --resource-group "$RESOURCE_GROUP" \
#   --server-name "$PG_SERVER" \
#   --database-name "your-database-name" 2>/dev/null || true

echo "Ensuring firewall rules exist..."
az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 2>/dev/null || true

az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAll \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 255.255.255.255 2>/dev/null || true

# 6. Create Azure Cache for Redis
if az redis show --resource-group "$RESOURCE_GROUP" --name "$REDIS_NAME" &>/dev/null; then
  echo "[6/7] Redis cache already exists, skipping."
else
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
fi

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
echo "  Example DB URL:"
echo "    postgresql://${PG_ADMIN_USER}:${PG_ADMIN_PASS}@${PG_SERVER}.postgres.database.azure.com:5432/agnirudra-app?sslmode=require"
echo ""
echo "  (Add your own databases using az postgres flexible-server db create)"
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
