#!/bin/bash
# Quick local Docker test — no credentials needed.
# Verifies: image builds, modules import, display pipeline works.
set -euo pipefail

IMAGE="agnirudra-test"
PASS=0
FAIL=0

info()  { echo -e "\033[1;34m[INFO]\033[0m $*"; }
pass()  { echo -e "\033[1;32m[PASS]\033[0m $*"; PASS=$((PASS+1)); }
fail()  { echo -e "\033[1;31m[FAIL]\033[0m $*"; FAIL=$((FAIL+1)); }

# --- Build ---
info "Building Docker image..."
docker build -t "$IMAGE" -f docker/agni-vm/Dockerfile . -q > /dev/null
pass "Docker image built"

run_check() {
    local desc="$1"; shift
    if docker run --rm --entrypoint bash "$IMAGE" -c "$*" > /dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc"
    fi
}

# --- Module imports ---
info "Testing module imports..."
run_check "import agnirudra"                    "python3 -c 'import agnirudra'"
run_check "import agent_loop"                   "python3 -c 'from agnirudra.agni.agent_loop import run_agent_loop'"
run_check "import storage"                      "python3 -c 'from agnirudra.agni.storage import upload_recording, upload_thumbnail'"
run_check "import github_reporter"              "python3 -c 'from agnirudra.agni.github_reporter import post_result'"
run_check "import computer tools"               "python3 -c 'from agnirudra.agni.tools import computer, bash_tool'"

# --- Display pipeline ---
info "Testing display pipeline..."
run_check "Xvfb starts"                         "Xvfb :99 -screen 0 1280x720x24 & sleep 1 && DISPLAY=:99 xdotool getdisplaygeometry > /dev/null 2>&1"
run_check "scrot takes screenshot"              "Xvfb :99 -screen 0 1280x720x24 & sleep 1 && DISPLAY=:99 scrot -o /tmp/test.png && test -s /tmp/test.png"
run_check "FFmpeg records and stops"            "Xvfb :99 -screen 0 1280x720x24 & sleep 1 && DISPLAY=:99 ffmpeg -y -f x11grab -video_size 1280x720 -framerate 15 -i :99 -c:v libx264 -preset ultrafast -t 2 /tmp/test.mp4 2>/dev/null && test -s /tmp/test.mp4"

# --- Browser wrapper ---
info "Testing browser wrapper..."
run_check "browser wrapper exists"              "test -x /usr/local/bin/browser"
run_check "browser --version works"             "browser --version > /dev/null 2>&1"

# --- Summary ---
echo ""
echo "================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
