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
PR_INFO=$(curl -s -H "Authorization: token ${AGNI_GITHUB_TOKEN}" \
  "https://api.github.com/repos/${AGNI_GITHUB_REPOSITORY}/pulls/${AGNI_PR_NUMBER}")
PR_REF=$(echo "$PR_INFO" | jq -r '.head.ref')
COMMIT_SHA=$(echo "$PR_INFO" | jq -r '.head.sha')

git fetch origin "+refs/heads/$PR_REF:refs/remotes/origin/$PR_REF"
git checkout -b "$PR_REF" "origin/$PR_REF"
echo "Checked out branch: $PR_REF (commit: ${COMMIT_SHA:0:8})"

# --- 5. Start services ---
echo "[5/10] Starting services..."

# Install pyyaml for config parsing
pip install pyyaml -q 2>/dev/null || true

start_services() {
  if [ -f .agni.yml ]; then
    echo "Found .agni.yml — using explicit config"
    python3 << 'PYEOF'
import yaml, subprocess, os, sys

with open(".agni.yml") as f:
    config = yaml.safe_load(f)

services = config.get("services", [])
if not services:
    # Backwards compat: single-service format
    install = config.get("install", "")
    dev = config.get("dev", "")
    path = config.get("path", ".")
    if install or dev:
        services = [{"name": "app", "path": path, "install": install, "dev": dev,
                      "port": config.get("port", 3000)}]

if not services:
    print("WARNING: .agni.yml has no services defined")
    sys.exit(1)

for svc in services:
    name = svc.get("name", "unknown")
    path = svc.get("path", ".")
    install_cmd = svc.get("install", "")
    dev_cmd = svc.get("dev", "")
    env_vars = svc.get("env", {})
    port = svc.get("port", 3000)

    full_path = os.path.join("/workspace", path)
    print(f"  [{name}] path={full_path} port={port}")

    # Build env with any service-specific vars merged with current env
    # Expand ${VAR} references in values against the current environment
    import re
    svc_env = os.environ.copy()
    for k, v in env_vars.items():
        v = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), str(v))
        svc_env[k] = v

    if install_cmd:
        print(f"  [{name}] install: {install_cmd}")
        result = subprocess.run(install_cmd, shell=True, cwd=full_path, env=svc_env)
        if result.returncode != 0:
            print(f"  ERROR: [{name}] install failed with exit code {result.returncode}")
            sys.exit(1)

    if dev_cmd:
        print(f"  [{name}] dev: {dev_cmd}")
        subprocess.Popen(dev_cmd, shell=True, cwd=full_path, env=svc_env,
                         stdout=open(f"/tmp/{name}.log", "w"),
                         stderr=subprocess.STDOUT)

print("All services started.")
PYEOF
    return $?
  fi

  # Auto-detect fallback (single project)
  if [ -f package.json ]; then
    echo "Detected Node.js project"
    npm install
    npm run dev &
    return 0
  fi

  if [ -f requirements.txt ]; then
    echo "Detected Python project"
    pip install -r requirements.txt
    if grep -q "uvicorn" requirements.txt || grep -q "fastapi" requirements.txt; then
      uvicorn main:app --host 0.0.0.0 --port 8000 &
    elif grep -q "flask" requirements.txt; then
      flask run --host=0.0.0.0 &
    elif grep -q "django" requirements.txt; then
      python manage.py runserver 0.0.0.0:8000 &
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

if ! start_services; then
  echo "FATAL: Service startup failed. Exiting."
  exit 1
fi

# --- 6. Wait for app to be ready ---
echo "[6/10] Waiting for services to be ready..."

# Parse the test_target port from .agni.yml, or check common ports
if [ -f .agni.yml ]; then
  TEST_PORT=$(python3 -c "
import yaml
with open('.agni.yml') as f:
    c = yaml.safe_load(f)
target = c.get('test_target', '')
for svc in c.get('services', []):
    if svc.get('name') == target:
        print(svc.get('port', 3000))
        break
else:
    print(c.get('port', 3000))
" 2>/dev/null || echo "3000")
  PORTS="$TEST_PORT"
else
  PORTS="3000 8000 5173 8080 4200 3001"
fi

# Wait for ALL defined service ports (not just the test target)
if [ -f .agni.yml ]; then
  ALL_PORTS=$(python3 -c "
import yaml
with open('.agni.yml') as f:
    c = yaml.safe_load(f)
ports = []
for svc in c.get('services', []):
    ports.append(str(svc.get('port', 3000)))
if not ports:
    ports = [str(c.get('port', 3000))]
print(' '.join(ports))
" 2>/dev/null || echo "$PORTS")
else
  ALL_PORTS="$PORTS"
fi

echo "Waiting for ports: $ALL_PORTS"
for port in $ALL_PORTS; do
  echo "  Waiting for port $port..."
  for i in $(seq 1 60); do
    if curl -s -o /dev/null -w "" "http://localhost:$port" 2>/dev/null; then
      echo "  Port $port is ready"
      break
    fi
    if [ "$i" -eq 60 ]; then
      echo "FATAL: Port $port did not become ready within 120s"
      # Dump service logs for debugging
      for logfile in /tmp/*.log; do
        [ -f "$logfile" ] && echo "=== $logfile ===" && tail -20 "$logfile"
      done
      exit 1
    fi
    sleep 2
  done
done

echo "Service readiness check complete."

# --- 7. Run the agent loop ---
echo "[7/10] Running Agni agent loop..."
DISPLAY=:1 python -m agnirudra.agni.agent_loop || {
  echo "WARNING: Agent loop exited with code $?"
}

# --- 8. Stop recording ---
echo "[8/10] Stopping screen recording..."
kill -INT "$FFMPEG_PID" 2>/dev/null || true
sleep 3
wait "$FFMPEG_PID" 2>/dev/null || true

# --- 9. Upload recording ---
echo "[9/10] Uploading recording to Azure Blob Storage..."
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
