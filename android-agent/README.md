# Android Agent MVP

## Phase A1
- Android application scaffold
- Foreground service
- Embedded local HTTP server

## Phase A2
- `POST /device/android-local/screenshot`
- `POST /device/android-local/tap`
- `POST /device/android-local/swipe`
- `POST /device/android-local/type_text`
- `GET /device/android-local/current_app`

## Runtime prerequisites
- Accessibility service enabled for gesture and text actions
- Screen capture permission granted for screenshot

## Verification entrypoints
- Structure check: `python3 scripts/check_android_agent_scaffold.py`
- Build: `cd android-agent && ANDROID_SDK_ROOT=/root/android-sdk ANDROID_HOME=/root/android-sdk ./gradlew assembleDebug`

## Phase A3 Draft: Emulator Integration Runbook

This section captures the minimum runtime evidence used to validate the Android Agent MVP on `emulator-5554`. It is intentionally command-first so QA or follow-up engineers can replay the same flow.

### Environment
- Repo root: `AutoGLM-GUI`
- Android project: `android-agent`
- Tested device: `emulator-5554`
- `adb` path used during validation: `/root/android-sdk/platform-tools/adb`
- APK output: `android-agent/app/build/outputs/apk/debug/app-debug.apk`
- Local HTTP port: `18080`

### Build and install
1. Build the debug APK:

```bash
cd android-agent
ANDROID_SDK_ROOT=/root/android-sdk ANDROID_HOME=/root/android-sdk ./gradlew assembleDebug
```

2. Install the APK onto the emulator:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
```

### Start the app and foreground service
1. Launch the activity:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 shell am start -S -n com.autoglm.agent/.MainActivity
```

2. Tap `Start agent` in the emulator UI. The validation run used this coordinate on the reference emulator:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 shell input tap 540 1134
```

3. Forward the local HTTP port so host-side `curl` can reach the in-app server:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 forward tcp:18080 tcp:18080
```

### Grant screen capture
1. Tap `Grant screen capture`:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 shell input tap 540 1608
```

2. Complete the Android system dialog. The validation run used:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 shell input tap 540 1165
/root/android-sdk/platform-tools/adb -s emulator-5554 shell input tap 540 1353
/root/android-sdk/platform-tools/adb -s emulator-5554 shell input tap 893 1701
```

After grant, the app should report screen capture as granted and the HTTP health endpoint should expose `screen_capture_ready=true`.

### Health check
Run:

```bash
curl -s http://127.0.0.1:18080/health
```

Expected shape:

```json
{"status":"ok","service":"android-agent","version":"0.2.0","accessibility_enabled":false,"screen_capture_ready":true}
```

### Foreground service presence
Run after starting the app and tapping `Start agent`:

```bash
/root/android-sdk/platform-tools/adb -s emulator-5554 shell dumpsys activity services com.autoglm.agent
```

Key lines from the validation run:

```text
* ServiceRecord{... com.autoglm.agent/.service.AgentForegroundService ...}
intent={act=com.autoglm.agent.action.START cmp=com.autoglm.agent/.service.AgentForegroundService}
startForegroundCount=1
isForeground=true foregroundId=1001 types=0x00000001
startRequested=true delayedStop=false stopIfKilled=false callStart=true lastStartId=2
```

### Repeated screenshot verification
The A2 screenshot fix was validated against repeated sequential requests after grant. Example command:

```bash
python3 - <<'PY'
import json, subprocess

cmd = [
    "curl",
    "-s",
    "-X",
    "POST",
    "http://127.0.0.1:18080/device/android-local/screenshot",
    "-H",
    "Content-Type: application/json",
    "-d",
    '{"timeout":10}',
]

for i in range(1, 6):
    raw = subprocess.check_output(cmd, text=True)
    data = json.loads(raw)
    print(i, {
        "width": data.get("width"),
        "height": data.get("height"),
        "base64_len": len(data.get("base64_data", "")),
        "error": data.get("error"),
    })
PY
```

Reference result from the validation run:

```text
1 {'width': 1080, 'height': 2400, 'base64_len': 31432, 'error': None}
2 {'width': 1080, 'height': 2400, 'base64_len': 31432, 'error': None}
3 {'width': 1080, 'height': 2400, 'base64_len': 31432, 'error': None}
4 {'width': 1080, 'height': 2400, 'base64_len': 31432, 'error': None}
5 {'width': 1080, 'height': 2400, 'base64_len': 31432, 'error': None}
```

### Notes
- `current_app`, `tap`, `swipe`, and `type_text` were already validated earlier against the in-app demo UI.
- Screenshot stability on Android 14 depends on reusing a single `MediaProjection + VirtualDisplay + ImageReader` session after permission grant.
- When the screen is static and no fresh frame arrives before timeout, the current implementation can return the most recent successful screenshot instead of failing the whole request.
