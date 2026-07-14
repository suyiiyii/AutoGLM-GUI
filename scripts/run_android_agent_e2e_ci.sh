#!/usr/bin/env bash
# Driver for the Android Agent E2E job. Kept as a standalone script because
# android-emulator-runner executes its `script:` input line-by-line, which
# breaks backslash line-continuations and does not persist `export`s across
# lines. Running everything in one shell process avoids both problems.
set -euo pipefail

# The reverse-agent path never calls the model, so a dummy model config is
# enough for the backend to boot (no secrets required).
export AUTOGLM_BASE_URL=http://localhost:8080/v1
export AUTOGLM_MODEL_NAME=test-model
export AUTOGLM_API_KEY=test-key

echo "starting backend..."
nohup uv run autoglm-gui --host 0.0.0.0 --port 8080 --base-url http://localhost:8080/v1 \
  > /tmp/backend.log 2>&1 &

echo "waiting for backend..."
for _ in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8080/api/health > /dev/null; then
    echo "backend ready"
    break
  fi
  sleep 1
done
if ! curl -sf http://127.0.0.1:8080/api/health > /dev/null; then
  echo "backend failed to start:"
  cat /tmp/backend.log
  exit 1
fi

echo "installing APK..."
adb install -r android-agent/app/build/outputs/apk/debug/app-debug.apk

echo "running e2e check..."
BASE_URL=http://127.0.0.1:8080 \
DEVICE_BASE_URL=http://10.0.2.2:8080 \
ARTIFACT_DIR="${GITHUB_WORKSPACE:-$PWD}/e2e-artifacts" \
  uv run python scripts/android_agent_e2e_check.py
