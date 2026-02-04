#!/bin/bash
# Build a pre-baked Azure VM image with Docker + Agni container cached.
#
# This eliminates ~1.5-2 min of setup time per test run by pre-installing
# Docker and pre-pulling the Agni Docker image.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - The agnirudra-rg resource group exists (run setup-azure.sh first)
#
# Usage:
#   ./scripts/build-vm-image.sh [docker-image] [resource-group] [location]
#
# Re-run this script whenever the Docker image is updated.

set -euo pipefail

DOCKER_IMAGE="${1:-ghcr.io/tabtabtabai/agnirudra:latest}"
RESOURCE_GROUP="${2:-agnirudra-rg}"
LOCATION="${3:-eastus}"
IMAGE_NAME="agnirudra-vm-image"
BUILDER_VM="agni-image-builder"

echo "=== Building Agni VM Image ==="
echo "Docker image: $DOCKER_IMAGE"
echo "Resource group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Output image: $IMAGE_NAME"
echo ""

# Clean up any previous builder VM
echo "[1/7] Cleaning up previous builder resources..."
az vm delete --resource-group "$RESOURCE_GROUP" --name "$BUILDER_VM" --yes --force-deletion yes 2>/dev/null || true
az network nic delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}VMNic" 2>/dev/null || true
az network public-ip delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}PublicIP" 2>/dev/null || true
az network nsg delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}NSG" 2>/dev/null || true

# Create cloud-init script
CLOUD_INIT=$(mktemp)
cat > "$CLOUD_INIT" <<EOF
#!/bin/bash
set -euo pipefail
curl -fsSL https://get.docker.com | sh
docker pull $DOCKER_IMAGE
echo "AGNI_IMAGE_READY" > /tmp/agni-image-ready
EOF

echo "[2/7] Creating builder VM..."
az vm create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BUILDER_VM" \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts:latest \
  --size Standard_D2s_v3 \
  --admin-username agni \
  --generate-ssh-keys \
  --location "$LOCATION" \
  --custom-data "$CLOUD_INIT" \
  --output none

rm -f "$CLOUD_INIT"

echo "[3/7] Waiting for Docker install + image pull to complete..."
for i in $(seq 1 60); do
  RESULT=$(az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name "$BUILDER_VM" \
    --command-id RunShellScript \
    --scripts 'cat /tmp/agni-image-ready 2>/dev/null || echo "NOT_READY"' \
    --query 'value[0].message' -o tsv 2>/dev/null || echo "NOT_READY")

  if echo "$RESULT" | grep -q "AGNI_IMAGE_READY"; then
    echo "  Docker and image are ready."
    break
  fi

  if [ "$i" -eq 60 ]; then
    echo "ERROR: Timed out waiting for cloud-init (10 min). Check VM logs."
    az vm delete --resource-group "$RESOURCE_GROUP" --name "$BUILDER_VM" --yes 2>/dev/null || true
    exit 1
  fi

  echo "  Waiting... ($i/60)"
  sleep 10
done

echo "[4/7] Deprovisioning VM..."
az vm run-command invoke \
  --resource-group "$RESOURCE_GROUP" \
  --name "$BUILDER_VM" \
  --command-id RunShellScript \
  --scripts 'sudo waagent -deprovision+user -force' \
  --output none 2>/dev/null || true

echo "[5/7] Deallocating and generalizing..."
az vm deallocate --resource-group "$RESOURCE_GROUP" --name "$BUILDER_VM"
az vm generalize --resource-group "$RESOURCE_GROUP" --name "$BUILDER_VM"

# Delete old image if it exists
az image delete --resource-group "$RESOURCE_GROUP" --name "$IMAGE_NAME" 2>/dev/null || true

echo "[6/7] Capturing image..."
az image create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$IMAGE_NAME" \
  --source "$BUILDER_VM" \
  --location "$LOCATION" \
  --output none

IMAGE_ID=$(az image show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$IMAGE_NAME" \
  --query 'id' -o tsv)

echo "[7/7] Cleaning up builder VM..."
az vm delete --resource-group "$RESOURCE_GROUP" --name "$BUILDER_VM" --yes --force-deletion yes 2>/dev/null || true
az network nic delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}VMNic" 2>/dev/null || true
az network public-ip delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}PublicIP" 2>/dev/null || true
az network nsg delete --resource-group "$RESOURCE_GROUP" --name "${BUILDER_VM}NSG" 2>/dev/null || true

echo ""
echo "=== Done ==="
echo "Image ID: $IMAGE_ID"
echo ""
echo "Add this to your GitHub Actions workflow secrets or action inputs:"
echo "  vm-image: $IMAGE_ID"
