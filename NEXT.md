# Next Steps

Priority fixes before testing on tabtabtab-sheets.

## 1. Pre-baked VM Image

Right now every test run boots a stock Ubuntu 22.04 VM, then cloud-init installs Docker, pulls the agnirudra image, and runs it. That's 3-5 minutes of dead time before the agent even starts.

### What to build

A custom Azure VM image (via Packer or `az image create`) with everything pre-installed:

- Docker CE
- The agnirudra Docker image already pulled
- Node.js 20, Python 3.11, Poetry (so app install inside the container is faster too)

### How

```bash
# 1. Create a temporary VM
az vm create \
  --resource-group agnirudra-rg \
  --name agnirudra-image-builder \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts:latest \
  --size Standard_D4s_v3 \
  --admin-username agni \
  --generate-ssh-keys

# 2. SSH in and install everything
ssh agni@<public-ip>
curl -fsSL https://get.docker.com | sh
docker pull ghcr.io/tabtabtabai/agnirudra:latest
# Install Node, Python, etc. if you want them on the host too

# 3. Deprovision and generalize
sudo waagent -deprovision+user -force
exit

# 4. Deallocate and capture
az vm deallocate --resource-group agnirudra-rg --name agnirudra-image-builder
az vm generalize --resource-group agnirudra-rg --name agnirudra-image-builder
az image create \
  --resource-group agnirudra-rg \
  --name agnirudra-base-image \
  --source agnirudra-image-builder

# 5. Clean up the builder VM
az vm delete --resource-group agnirudra-rg --name agnirudra-image-builder --yes
```

### Code change in vm.py

Replace the Canonical image reference with the custom image:

```python
# Before
image_reference=ImageReference(
    publisher="Canonical",
    offer="0001-com-ubuntu-server-jammy",
    sku="22_04-lts",
    version="latest",
)

# After
image_reference=ImageReference(
    id="/subscriptions/<sub-id>/resourceGroups/agnirudra-rg/providers/Microsoft.Compute/images/agnirudra-base-image"
)
```

And simplify cloud-init to skip the Docker install:

```bash
#!/bin/bash
set -euo pipefail
# Docker is already installed, image is already pulled
docker run --rm $ENV_ARGS ghcr.io/tabtabtabai/agnirudra:latest
```

### Impact

Boot-to-agent time drops from ~5 minutes to ~30 seconds. On a 10-minute timeout budget, that's the difference between 5 minutes of actual testing vs 10 minutes.

### Maintenance

Rebuild the image when you update the agnirudra Docker image. Add a GitHub Actions workflow that rebuilds it on release:

```yaml
# .github/workflows/build-image.yml
name: Build Azure VM Image
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-packer@v3
      - run: packer build packer/agnirudra-base.pkr.hcl
```

A Packer template (`packer/agnirudra-base.pkr.hcl`) is the proper way to do this repeatably. The manual `az` commands above are for a one-off first image.

---

## 2. Move Secrets Out of Cloud-Init

Cloud-init custom data is base64-encoded and visible to anyone with Reader access on the resource group via the Azure portal or API. All secrets (Anthropic key, GitHub token, DB credentials) are currently embedded there in plaintext.

### Fix

Use Azure Key Vault:

1. Create a Key Vault in `agnirudra-rg` (one-time setup)
2. Store secrets there instead of passing them inline
3. Give the VM a system-assigned managed identity
4. Grant that identity `Secret Reader` on the Key Vault
5. Cloud-init fetches secrets from Key Vault at runtime

```bash
# One-time setup
az keyvault create --name agnirudra-kv --resource-group agnirudra-rg --location eastus

# The orchestrator stores secrets per-run
az keyvault secret set --vault-name agnirudra-kv --name "run-<pr>-<hash>" --value '<json blob>'
```

Cloud-init becomes:

```bash
#!/bin/bash
set -euo pipefail

# Fetch secrets using the VM's managed identity
TOKEN=$(curl -s -H "Metadata:true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://vault.azure.net" \
  | jq -r .access_token)

SECRETS=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://agnirudra-kv.vault.azure.net/secrets/run-${PR_NUMBER}-${COMMIT_HASH}?api-version=7.4" \
  | jq -r .value)

# Parse and export
eval $(echo "$SECRETS" | jq -r 'to_entries[] | "export \(.key)=\(.value | @sh)"')

docker run --rm --env-file <(env | grep -E '^(AGNI_|DATABASE_|REDIS_|OPENAI_)') \
  ghcr.io/tabtabtabai/agnirudra:latest
```

The orchestrator writes the secrets to Key Vault before creating the VM, and cleans them up during teardown. Secrets never appear in Azure VM metadata.

---

## 3. VM Health Check (Fail Fast on Crashes)

Currently the orchestrator polls only for `done.marker` in blob storage. If the VM crashes, it waits the full 10-minute timeout before giving up.

### Fix

Poll both the blob marker AND the VM power state:

```python
def poll_for_completion(settings, commit_hash, timeout=None):
    # ...existing blob polling...

    # Additionally check if VM is still running
    vm = compute_client.virtual_machines.get(
        rg, vm_name, expand="instanceView"
    )
    power_state = next(
        (s.code for s in vm.instance_view.statuses if s.code.startswith("PowerState/")),
        ""
    )
    if power_state in ("PowerState/deallocated", "PowerState/stopped"):
        logger.error("VM %s is %s but no done marker found", vm_name, power_state)
        return False  # Fail immediately instead of waiting
```

This cuts failure detection from 10 minutes to ~15 seconds (one poll cycle).

---

## 4. Bump Timeout Budget

Change the default from 600s (10 min) to 900s (15 min) in config.py:

```python
vm_timeout_seconds: int = Field(
    default=900, description="Max seconds to wait for VM completion"
)
```

With the pre-baked image, 15 minutes gives ~14 minutes of actual test time. Without it, 15 minutes gives ~10 minutes. Either way, more breathing room for monorepos with 4 services that need `npm install` + `poetry install`.

---

## Build Order

1. **Pre-baked image** — biggest impact, do this first
2. **Bump timeout** — one-line change, do it alongside
3. **VM health check** — small code change, high value
4. **Key Vault secrets** — important for security, but the current approach works for private testing
