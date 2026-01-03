import argparse
import base64
from pathlib import Path
from phone_agent.adb.connection import quick_connect, list_devices
from phone_agent.adb.device import tap, swipe, back, home, get_current_app, launch_app
from phone_agent.adb.screenshot import get_screenshot


def pick_device_id(device_id: str | None) -> str | None:
    if device_id:
        return device_id
    devices = list_devices()
    for d in devices:
        if d.status == "device":
            return d.device_id
    return None


def save_base64_png(b64: str, out_path: str) -> None:
    data = base64.b64decode(b64)
    Path(out_path).write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", type=str)
    parser.add_argument("--device-id", type=str)
    parser.add_argument("--tap", nargs=2, type=int)
    parser.add_argument("--double-tap", nargs=2, type=int)
    parser.add_argument("--long-press", nargs=3, type=int)
    parser.add_argument("--swipe", nargs=5, type=int)
    parser.add_argument("--back", action="store_true")
    parser.add_argument("--home", action="store_true")
    parser.add_argument("--launch-app", type=str)
    parser.add_argument("--current-app", action="store_true")
    parser.add_argument("--screenshot", type=str)
    args = parser.parse_args()

    if args.address:
        ok, msg = quick_connect(args.address)
        print(msg)

    device_id = pick_device_id(args.device_id)

    if args.tap and device_id:
        x, y = args.tap
        tap(x, y, device_id=device_id)
        print(f"tap {x},{y}")

    if args.double_tap and device_id:
        x, y = args.double_tap
        from phone_agent.adb.device import double_tap

        double_tap(x, y, device_id=device_id)
        print(f"double_tap {x},{y}")

    if args.long_press and device_id:
        x, y, duration_ms = args.long_press
        from phone_agent.adb.device import long_press

        long_press(x, y, duration_ms=duration_ms, device_id=device_id)
        print(f"long_press {x},{y},{duration_ms}ms")

    if args.swipe and device_id:
        sx, sy, ex, ey, dur = args.swipe
        swipe(sx, sy, ex, ey, duration_ms=dur, device_id=device_id)
        print(f"swipe {sx},{sy}->{ex},{ey} {dur}ms")

    if args.back and device_id:
        back(device_id=device_id)
        print("back")

    if args.home and device_id:
        home(device_id=device_id)
        print("home")

    if args.launch_app and device_id:
        ok = launch_app(args.launch_app, device_id=device_id)
        print(f"launch_app {args.launch_app} {ok}")

    if args.current_app and device_id:
        app = get_current_app(device_id=device_id)
        print(f"current_app {app}")

    if args.screenshot and device_id:
        shot = get_screenshot(device_id=device_id)
        save_base64_png(shot.base64_data, args.screenshot)
        print(
            f"screenshot {args.screenshot} {shot.width}x{shot.height} sensitive={shot.is_sensitive}"
        )


if __name__ == "__main__":
    main()
