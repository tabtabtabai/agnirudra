#!/bin/bash
# Run the full agent loop locally against a running app.
#
# Usage:
#   AGNI_ANTHROPIC_API_KEY=sk-ant-xxx ./scripts/test-local-agent.sh [url]
#
# Arguments:
#   url   The app URL to test (default: http://host.docker.internal:3000)
#
# Output:
#   test-output/recording.mp4  — screen recording of the test
#   test-output/verdict.json   — pass/fail verdict
set -euo pipefail

IMAGE="agnirudra-test"
TEST_URL="${1:-http://host.docker.internal:3000}"
OUTPUT_DIR="test-output"

if [ -z "${AGNI_ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: AGNI_ANTHROPIC_API_KEY is required"
    echo "Usage: AGNI_ANTHROPIC_API_KEY=sk-ant-xxx $0 [url]"
    exit 1
fi

echo "Building Docker image..."
docker build -t "$IMAGE" -f docker/agni-vm/Dockerfile . -q > /dev/null

mkdir -p "$OUTPUT_DIR"
CONTAINER_NAME="agni-local-test-$$"

TEST_PLAN=$(cat <<EOF
{
    "description": "Verify the app loads and is functional",
    "start_url": "${TEST_URL}",
    "pass_criteria": "The app loads successfully and shows content",
    "fail_criteria": "The app fails to load or shows errors",
    "steps": [
        "Open the browser and navigate to the start URL",
        "Wait for the page to fully load",
        "Take a screenshot and verify the page has content",
        "Write your verdict"
    ]
}
EOF
)

echo "Starting agent loop against ${TEST_URL}..."
echo "Container: ${CONTAINER_NAME}"
echo ""

docker run --rm --name "$CONTAINER_NAME" \
    --add-host=host.docker.internal:host-gateway \
    --entrypoint bash \
    -e AGNI_ANTHROPIC_API_KEY="$AGNI_ANTHROPIC_API_KEY" \
    -e AGNI_MODEL="${AGNI_MODEL:-claude-sonnet-4-5-20250929}" \
    -e TEST_PLAN="$TEST_PLAN" \
    -e DISPLAY=:1 \
    -v "$(pwd)/$OUTPUT_DIR:/output" \
    "$IMAGE" -c '
set -euo pipefail

echo "[1/5] Starting Xvfb..."
Xvfb :1 -screen 0 1280x720x24 &
sleep 1

echo "[2/5] Starting openbox..."
DISPLAY=:1 openbox &
sleep 1

echo "[3/5] Starting screen recording..."
DISPLAY=:1 ffmpeg -y \
  -f x11grab -video_size 1280x720 -framerate 15 -i :1 \
  -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p \
  /tmp/recording.mp4 &
FFMPEG_PID=$!
sleep 1

echo "[4/5] Running agent loop..."
DISPLAY=:1 python -m agnirudra.agni.agent_loop || {
    echo "WARNING: Agent loop exited with code $?"
}

echo "[5/5] Stopping recording..."
kill -INT "$FFMPEG_PID" 2>/dev/null || true
sleep 3
wait "$FFMPEG_PID" 2>/dev/null || true

# Extract thumbnail
ffmpeg -y -sseof -3 -i /tmp/recording.mp4 -frames:v 1 -q:v 2 /tmp/thumbnail.jpg 2>/dev/null || true

# Copy outputs
cp /tmp/recording.mp4 /output/ 2>/dev/null || echo "No recording produced"
cp /tmp/thumbnail.jpg /output/ 2>/dev/null || echo "No thumbnail produced"
cp /tmp/verdict.json /output/ 2>/dev/null || echo "No verdict produced"

echo ""
echo "=== Done ==="
if [ -f /tmp/verdict.json ]; then
    echo "Verdict: $(cat /tmp/verdict.json)"
else
    echo "No verdict file produced"
fi
'

echo ""
echo "Output files:"
ls -la "$OUTPUT_DIR/" 2>/dev/null || echo "  (none)"
