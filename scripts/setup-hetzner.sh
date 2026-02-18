#!/bin/bash
# One-time Hetzner Cloud resource setup for Agnirudra
#
# This script helps you set up the necessary Hetzner resources:
# 1. API token (for VM creation)
# 2. Object Storage bucket (for recordings)
#
# Prerequisites:
#   - Hetzner Cloud account (https://console.hetzner.cloud)
#   - Hetzner Object Storage enabled (https://console.hetzner.cloud/objectstorage)
#
# Usage:
#   ./scripts/setup-hetzner.sh

set -euo pipefail

echo "=== Agnirudra Hetzner Setup ==="
echo ""
echo "This script will guide you through setting up Hetzner resources for Agnirudra."
echo ""

# Step 1: API Token
echo "=== Step 1: Create API Token ==="
echo ""
echo "1. Go to: https://console.hetzner.cloud/projects"
echo "2. Select your project (or create a new one)"
echo "3. Go to Security → API Tokens"
echo "4. Click 'Generate API Token'"
echo "5. Name it 'agnirudra-gh-actions' and select 'Read & Write'"
echo "6. Copy the token (you won't be able to see it again)"
echo ""
read -rp "Enter your Hetzner API token: " HETZNER_API_TOKEN

if [ -z "$HETZNER_API_TOKEN" ]; then
  echo "ERROR: API token is required"
  exit 1
fi

# Validate token by listing servers
echo "Validating API token..."
if ! curl -s -H "Authorization: Bearer $HETZNER_API_TOKEN" \
  "https://api.hetzner.cloud/v1/servers" | grep -q '"servers"'; then
  echo "ERROR: Invalid API token"
  exit 1
fi
echo "API token is valid!"
echo ""

# Step 2: Object Storage
echo "=== Step 2: Set up Object Storage ==="
echo ""
echo "1. Go to: https://console.hetzner.cloud/objectstorage"
echo "2. Create a new bucket named 'agnirudra-recordings'"
echo "3. Note the endpoint URL (e.g., https://fsn1.your-objectstorage.com)"
echo "4. Go to 'Access Keys' and create a new access key"
echo ""

read -rp "Enter your S3 endpoint URL (e.g., https://fsn1.your-objectstorage.com): " S3_ENDPOINT
read -rp "Enter your S3 access key: " S3_ACCESS_KEY
read -rp "Enter your S3 secret key: " S3_SECRET_KEY
read -rp "Enter your bucket name [agnirudra-recordings]: " S3_BUCKET
S3_BUCKET="${S3_BUCKET:-agnirudra-recordings}"

# Extract region from endpoint
S3_REGION=$(echo "$S3_ENDPOINT" | sed -E 's|https://([^.]+)\..*|\1|')

echo ""
echo "=== Step 3: Verify Object Storage ==="
echo "Creating test file in bucket..."

# Try to create the bucket (may already exist)
AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
aws s3api create-bucket \
  --endpoint-url "$S3_ENDPOINT" \
  --bucket "$S3_BUCKET" 2>/dev/null || true

# Upload a test file
echo "test" | AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
aws s3 cp - "s3://$S3_BUCKET/test.txt" \
  --endpoint-url "$S3_ENDPOINT" 2>/dev/null && \
  echo "Object Storage is working!" || \
  echo "WARNING: Could not verify Object Storage (you may need to create the bucket manually)"

echo ""
echo "============================================================"
echo "  AGNIRUDRA HETZNER SETUP COMPLETE"
echo "============================================================"
echo ""
echo "Add these secrets to your GitHub repository:"
echo ""
echo "  HETZNER_API_TOKEN=$HETZNER_API_TOKEN"
echo "  HETZNER_S3_ENDPOINT=$S3_ENDPOINT"
echo "  HETZNER_S3_REGION=$S3_REGION"
echo "  HETZNER_S3_ACCESS_KEY=$S3_ACCESS_KEY"
echo "  HETZNER_S3_SECRET_KEY=$S3_SECRET_KEY"
echo "  HETZNER_S3_BUCKET=$S3_BUCKET"
echo ""
echo "Then update your workflow to use Hetzner:"
echo ""
echo "  - uses: your-org/agnirudra@main"
echo "    with:"
echo "      cloud-provider: hetzner"
echo "      docker-image: ghcr.io/your-org/agnirudra:latest"
echo "      hetzner-api-token: \${{ secrets.HETZNER_API_TOKEN }}"
echo "      hetzner-s3-endpoint: \${{ secrets.HETZNER_S3_ENDPOINT }}"
echo "      hetzner-s3-region: \${{ secrets.HETZNER_S3_REGION }}"
echo "      hetzner-s3-access-key: \${{ secrets.HETZNER_S3_ACCESS_KEY }}"
echo "      hetzner-s3-secret-key: \${{ secrets.HETZNER_S3_SECRET_KEY }}"
echo "      hetzner-s3-bucket: \${{ secrets.HETZNER_S3_BUCKET }}"
echo "      anthropic-api-key: \${{ secrets.ANTHROPIC_API_KEY }}"
echo "      github-token: \${{ secrets.GITHUB_TOKEN }}"
echo ""
