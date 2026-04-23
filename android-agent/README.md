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
