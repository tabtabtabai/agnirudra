# Agnirudra

AI-powered visual QA testing and code review for pull requests.

## Components

### Agni (Active)

GitHub Action that triggers on PR events from `claude/**` branches, spins up an Azure VM with a browser, uses Claude Opus 4.5 computer-use to visually test the feature, records the screen, and posts the video as a PR comment.

### Rudra (Design Only)

Smart single-pass code review bot. See [src/agnirudra/rudra/README.md](src/agnirudra/rudra/README.md) for the design document.

## Quick Start

### 1. Azure Setup (one-time)

```bash
./scripts/setup-azure.sh <your-subscription-id>
```

### 2. Add to Your Repo

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
      - uses: tabtabtabai/agnirudra@main
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          azure-credentials: ${{ secrets.AZURE_CREDENTIALS }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### 3. Optional: App Config

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
3. If UI changes detected, spins up an Azure VM with browser + screen recording
4. Claude computer-use agent navigates the app and tests the changes
5. Recording uploaded to Azure Blob Storage
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

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `AZURE_CREDENTIALS` | Azure SP credentials JSON (from setup script) |
| `GITHUB_TOKEN` | Automatically provided by GitHub Actions |

## License

GPLv3 - see [LICENSE](LICENSE).
