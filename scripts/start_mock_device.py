#!/usr/bin/env python3
"""
Mock Device Agent 启动脚本

用法:
    uv run python scripts/start_mock_device.py                    # 默认 18000 端口
    uv run python scripts/start_mock_device.py --port 8001        # 自定义端口
    uv run python scripts/start_mock_device.py --scenario path/to/scenario.yaml  # 加载场景

功能:
    - 模拟 Android 设备，接收 tap、swipe、screenshot 等命令
    - 记录所有操作，可通过 HTTP API 查询
    - 支持加载测试场景（状态机），返回真实截图和状态转换
"""

import argparse
import time
import threading

import httpx
import uvicorn


def _load_scenario_after_startup(base_url: str, scenario_path: str, delay: float = 1.0):
    """等待服务器启动后加载场景。"""
    time.sleep(delay)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base_url}/test/load_scenario",
                json={"scenario_path": scenario_path},
            )
            resp.raise_for_status()
            result = resp.json()
            print(
                f"\n  ✓ 场景加载成功: {result.get('scenario', scenario_path)}",
                flush=True,
            )
            if result.get("states"):
                print(f"  可用状态: {', '.join(result['states'])}", flush=True)
    except Exception as e:
        print(f"\n  ❌ 场景加载失败: {e}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="启动 Mock Device Agent 服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 默认 18000 端口
  %(prog)s --port 8001              # 自定义端口
  %(prog)s --scenario tests/integration/fixtures/scenarios/meituan_message/scenario.yaml

测试 API:
  http://localhost:18000/test/commands       # 获取记录的命令
  http://localhost:18000/test/reset          # 重置命令历史
  http://localhost:18000/devices             # 获取设备列表
        """,
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=18000,
        help="服务器端口 (默认: 18000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址 (默认: 0.0.0.0)",
    )
    parser.add_argument(
        "--scenario",
        "-s",
        type=str,
        default="tests/integration/fixtures/scenarios/meituan_message/scenario.yaml",
        help="预加载的测试场景 YAML 文件路径 (默认: meituan_message)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="日志级别 (默认: info)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用自动重载（开发模式）",
    )

    args = parser.parse_args()

    # 导入并创建 app
    from tests.integration.device_agent.mock_agent_server import create_app

    app = create_app()

    # 构建服务器 URL
    server_url = f"http://localhost:{args.port}"

    print("=" * 60)
    print("  Mock Device Agent 服务器")
    print("=" * 60)
    print(f"  地址: http://{args.host}:{args.port}")
    print(f"  日志: {args.log_level}")
    if args.scenario:
        print(f"  场景: {args.scenario} (启动后自动加载)")
    print("=" * 60)
    print("\n可用端点:")
    print("  GET  /devices                    # 设备列表")
    print("  POST /device/{id}/screenshot     # 截图")
    print("  POST /device/{id}/tap            # 点击")
    print("  POST /device/{id}/swipe          # 滑动")
    print("  POST /device/{id}/type_text      # 输入文本")
    print("  POST /device/{id}/back           # 返回")
    print("\n测试 API:")
    print("  GET  /test/commands               # 命令历史")
    print("  POST /test/reset                  # 重置")
    print("  POST /test/load_scenario          # 加载场景")
    print("  GET  /test/state                  # 当前状态")
    print("=" * 60)
    print()

    # 如果有场景，启动后台线程在服务器启动后加载
    if args.scenario:
        load_thread = threading.Thread(
            target=_load_scenario_after_startup,
            args=(server_url, args.scenario),
            daemon=True,
        )
        load_thread.start()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
