import subprocess
import sys
import asyncio
from AutoGLM_GUI.platform_utils import is_windows, spawn_process

BASE_PORT = 8100
processes = []


async def _wait_process(p):
    if is_windows():
        return await asyncio.to_thread(p.wait)
    return await p.wait()


async def get_udids() -> list[str]:
    try:
        output = await asyncio.to_thread(
            subprocess.check_output,
            ["idevice_id", "-l"],
            text=True,
        )
        lines = output.strip().splitlines()
        return [line.strip() for line in lines if line.strip()]
    except FileNotFoundError:
        print("❌ idevice_id not found (install libimobiledevice)", file=sys.stderr)
        return []
    except Exception:
        print("❌ Failed to run idevice_id -l", file=sys.stderr)
        return []


async def setup():
    udids = await get_udids()

    if not udids:
        print("❌ No iOS devices found", file=sys.stderr)
        return

    for i, udid in enumerate(udids):
        port = BASE_PORT + i
        print(f"▶ {udid} -> localhost:{port}")

        # 启动 WebDriverAgent
        xcode_cmd = [
            "xcodebuild",
            "-project",
            "WebDriverAgent/WebDriverAgent.xcodeproj",
            "-scheme",
            "WebDriverAgentRunner",
            "-destination",
            f"platform=iOS,id={udid}",
            "test",
        ]
        p1 = await spawn_process(xcode_cmd)
        processes.append(p1)

        # 等 2 秒再启动 iproxy
        await asyncio.sleep(2)

        iproxy_cmd = ["iproxy", str(port), "8100", udid]
        p2 = await spawn_process(iproxy_cmd)
        processes.append(p2)

    # 等待所有子进程
    await asyncio.gather(*[_wait_process(p) for p in processes])


if __name__ == "__main__":
    asyncio.run(setup())
