# Next Steps

Priority improvements for Agnirudra.

## 1. Pre-baked VM Image (Azure)

Right now every test run boots a stock Ubuntu 22.04 VM, then cloud-init installs Docker, pulls the agnirudra image, and runs it. That's 3-5 minutes of dead time before the agent even starts.

### What to build

A custom Azure VM image (via Packer or `az image create`) with everything pre-installed:

- Docker CE
- The agnirudra Docker image already pulled
- Node.js 20, Python 3.11, Poetry (so app install inside the container is faster too)

### How

Use the provided script:

```bash
./scripts/build-vm-image.sh ghcr.io/your-org/agnirudra:latest
```

This creates a custom image and outputs the image ID to use in your workflow:

```yaml
- uses: your-org/agnirudra@main
  with:
    vm-image: /subscriptions/<sub-id>/resourceGroups/agnirudra-rg/providers/Microsoft.Compute/images/agnirudra-vm-image
```

### Impact

Boot-to-agent time drops from ~5 minutes to ~30 seconds. On a 10-minute timeout budget, that's the difference between 5 minutes of actual testing vs 10 minutes.

### Maintenance

Rebuild the image when you update the agnirudra Docker image. Add a GitHub Actions workflow that rebuilds it on release.

---

## 2. Move Secrets Out of Cloud-Init (Azure)

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

The orchestrator writes the secrets to Key Vault before creating the VM, and cleans them up during teardown. Secrets never appear in Azure VM metadata.

---

## 3. VM Health Check (Fail Fast on Crashes)

Currently the orchestrator polls only for `done.marker` in blob storage. If the VM crashes, it waits the full timeout before giving up.

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

## 4. Add More Cloud Providers

The infrastructure is now abstracted via the `CloudProvider` interface. Adding new providers requires:

1. Implement the `CloudProvider` base class in `src/agnirudra/agni/cloud/`
2. Add configuration fields to `AgniSettings` in `config.py`
3. Register the provider in `cloud/__init__.py`
4. Add inputs to `action.yml`
5. Create a setup script in `scripts/`

Potential providers to add:
- AWS (EC2 + S3)
- Google Cloud (Compute Engine + Cloud Storage)
- DigitalOcean (Droplets + Spaces)
- Vultr
- Linode

---

## Build Order

1. **Pre-baked image** — biggest impact, do this first
2. **VM health check** — small code change, high value
3. **Key Vault secrets** — important for security
4. **More cloud providers** — nice to have for broader adoption
