# Agnirudra

AI-powered visual QA testing and code review for pull requests.

## Components

### Agni (Active)

GitHub Action that triggers on PR events from `claude/**` branches, spins up a cloud VM with a browser, uses Claude Opus 4.5 computer-use to visually test the feature, records the screen, and posts the video as a PR comment.

**Supported Cloud Providers:**
- **Azure** - VMs + Blob Storage
- **Hetzner** - Cloud Servers + S3-compatible Object Storage

### Rudra (Design Only)

Smart single-pass code review bot. See [src/agnirudra/rudra/README.md](src/agnirudra/rudra/README.md) for the design document.

## Quick Start

### Option A: Azure Setup

```bash
# One-time setup
./scripts/setup-azure.sh <your-subscription-id>
```

Create `.github/workflows/agni.yml`:

```yaml
name: Agni Visual Test
on:
  pull_request:
    types: [opened, synchronize]
    branches: [main, master]
jobs:
  agni:
    runs-on: ubuntu-latest
    if: startsWith(github.head_ref, 'claude/')
    steps:
      - uses: your-org/agnirudra@main
        with:
          cloud-provider: azure
          docker-image: ghcr.io/your-org/agnirudra:latest
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          azure-credentials: ${{ secrets.AZURE_CREDENTIALS }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Option B: Hetzner Setup

```bash
# One-time setup
./scripts/setup-hetzner.sh
```

Create `.github/workflows/agni.yml`:

```yaml
name: Agni Visual Test
on:
  pull_request:
    types: [opened, synchronize]
    branches: [main, master]
jobs:
  agni:
    runs-on: ubuntu-latest
    if: startsWith(github.head_ref, 'claude/')
    steps:
      - uses: your-org/agnirudra@main
        with:
          cloud-provider: hetzner
          docker-image: ghcr.io/your-org/agnirudra:latest
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          hetzner-api-token: ${{ secrets.HETZNER_API_TOKEN }}
          hetzner-s3-endpoint: ${{ secrets.HETZNER_S3_ENDPOINT }}
          hetzner-s3-access-key: ${{ secrets.HETZNER_S3_ACCESS_KEY }}
          hetzner-s3-secret-key: ${{ secrets.HETZNER_S3_SECRET_KEY }}
          hetzner-s3-bucket: ${{ secrets.HETZNER_S3_BUCKET }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### App Configuration (Optional)

Add `.agni.yml` to your repo root for explicit app configuration:

```yaml
install: "npm install"
dev: "npm run dev"
port: 3000
base_url: "http://localhost:3000"
```

## How It Works

1. PR opened/updated on a `claude/**` branch
2. Agni fetches the diff, sends to Claude to generate a test plan
3. If UI changes detected, spins up a cloud VM with browser + screen recording
4. Claude computer-use agent navigates the app and tests the changes
5. Recording uploaded to cloud object storage
6. Pass/fail result posted as a PR comment with video link
7. VM cleaned up

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest -v

# Build Docker image
docker build -t agnirudra:test -f docker/agni-vm/Dockerfile .
```

## Required Secrets

### Azure

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `AZURE_CREDENTIALS` | Azure SP credentials JSON (from setup script) |
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions |

### Hetzner

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `HETZNER_API_TOKEN` | Hetzner Cloud API token |
| `HETZNER_S3_ENDPOINT` | Object Storage endpoint URL |
| `HETZNER_S3_ACCESS_KEY` | Object Storage access key |
| `HETZNER_S3_SECRET_KEY` | Object Storage secret key |
| `HETZNER_S3_BUCKET` | Object Storage bucket name |
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions |

## License

GPLv3 - see [LICENSE](LICENSE).
