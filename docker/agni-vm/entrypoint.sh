#!/bin/bash
set -euo pipefail

echo "=== Agni Test VM starting ==="

# --- 1. Start virtual display ---
echo "[1/10] Starting Xvfb..."
Xvfb :1 -screen 0 1280x720x24 &
sleep 1

# --- 2. Start window manager ---
echo "[2/10] Starting mutter..."
DISPLAY=:1 mutter --replace --sm-disable &
sleep 2

# --- 3. Start screen recording ---
echo "[3/10] Starting FFmpeg screen recording..."
DISPLAY=:1 ffmpeg -y \
  -f x11grab -video_size 1280x720 -framerate 15 -i :1 \
  -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p \
  /tmp/recording.mp4 &
FFMPEG_PID=$!
sleep 1

# --- 4. Clone repo and checkout PR branch ---
echo "[4/10] Cloning repository..."
REPO_URL="https://x-access-token:${AGNI_GITHUB_TOKEN}@github.com/${AGNI_GITHUB_REPOSITORY}.git"
git clone --depth=50 "$REPO_URL" /workspace
cd /workspace

# Fetch the PR branch
PR_REF=$(curl -s -H "Authorization: token ${AGNI_GITHUB_TOKEN}" \
  "https://api.github.com/repos/${AGNI_GITHUB_REPOSITORY}/pulls/${AGNI_PR_NUMBER}" \
  | jq -r '.head.ref')
COMMIT_SHA=$(curl -s -H "Authorization: token ${AGNI_GITHUB_TOKEN}" \
  "https://api.github.com/repos/${AGNI_GITHUB_REPOSITORY}/pulls/${AGNI_PR_NUMBER}" \
  | jq -r '.head.sha')

git fetch origin "$PR_REF"
git checkout "$PR_REF"
echo "Checked out branch: $PR_REF (commit: ${COMMIT_SHA:0:8})"

# --- 5. Detect app type and start dev server ---
echo "[5/10] Detecting app type and starting dev server..."

start_app() {
  # Check for explicit .agni.yml config
  if [ -f .agni.yml ]; then
    INSTALL_CMD=$(python3 -c "import yaml; print(yaml.safe_load(open('.agni.yml'))['install'])" 2>/dev/null || echo "")
    DEV_CMD=$(python3 -c "import yaml; print(yaml.safe_load(open('.agni.yml'))['dev'])" 2>/dev/null || echo "")
    if [ -n "$INSTALL_CMD" ]; then
      echo "Running install: $INSTALL_CMD"
      eval "$INSTALL_CMD"
    fi
    if [ -n "$DEV_CMD" ]; then
      echo "Running dev server: $DEV_CMD"
      eval "$DEV_CMD" &
      return 0
    fi
  fi

  # Auto-detect based on files present
  if [ -f package.json ]; then
    echo "Detected Node.js project"
    npm install
    npm run dev &
    return 0
  fi

  if [ -f requirements.txt ]; then
    echo "Detected Python project"
    pip install -r requirements.txt
    # Try common dev server commands
    if grep -q "flask" requirements.txt; then
      flask run --host=0.0.0.0 &
    elif grep -q "django" requirements.txt; then
      python manage.py runserver 0.0.0.0:8000 &
    elif grep -q "uvicorn" requirements.txt || grep -q "fastapi" requirements.txt; then
      uvicorn main:app --host 0.0.0.0 --port 8000 &
    else
      python -m http.server 8000 &
    fi
    return 0
  fi

  if [ -f docker-compose.yml ] || [ -f docker-compose.yaml ]; then
    echo "Detected Docker Compose project"
    docker compose up -d &
    return 0
  fi

  echo "WARNING: Could not detect app type"
  return 1
}

start_app || echo "App detection failed, agent will try to handle it"

# --- 6. Wait for app to be ready ---
echo "[6/10] Waiting for app to be ready..."
PORTS="3000 8000 5173 8080 4200 3001"
APP_READY=false
for i in $(seq 1 60); do
  for port in $PORTS; do
    if curl -s -o /dev/null -w "" "http://localhost:$port" 2>/dev/null; then
      echo "App is ready on port $port"
      APP_READY=true
      break 2
    fi
  done
  sleep 2
done

if [ "$APP_READY" = false ]; then
  echo "WARNING: App did not become ready on any standard port within 120s"
fi

# --- 7. Run the agent loop ---
echo "[7/10] Running Agni agent loop..."
DISPLAY=:1 python -m agnirudra.agni.agent_loop || true

# --- 8. Stop recording ---
echo "[8/10] Stopping screen recording..."
kill -INT "$FFMPEG_PID" 2>/dev/null || true
sleep 3
# Wait for FFmpeg to finalize the MP4
wait "$FFMPEG_PID" 2>/dev/null || true

# --- 9. Upload recording ---
echo "[9/10] Uploading recording to Azure Blob Storage..."
COMMIT_SHORT="${COMMIT_SHA:0:8}"
python3 -c "
import json
from pathlib import Path
from agnirudra.agni.storage import upload_recording, generate_sas_url, write_done_marker
from agnirudra.config import AgniSettings
from agnirudra.agni.github_reporter import post_result, post_error

settings = AgniSettings()
commit_hash = '${COMMIT_SHA}'

# Upload recording
blob_path = upload_recording(settings, Path('/tmp/recording.mp4'), commit_hash)
recording_url = generate_sas_url(settings, blob_path)

# Read verdict
verdict = {'passed': False, 'summary': 'Agent did not produce a verdict'}
verdict_path = Path('/tmp/verdict.json')
if verdict_path.exists():
    verdict = json.loads(verdict_path.read_text())

# Post PR comment
post_result(
    settings,
    passed=verdict.get('passed', False),
    summary=verdict.get('summary', 'No summary'),
    recording_url=recording_url,
    commit_hash=commit_hash,
    commit_message='${PR_REF}',
)

# Write done marker
write_done_marker(settings, commit_hash)
print('Done! Results posted to PR.')
"

echo "[10/10] Complete. Exiting."
