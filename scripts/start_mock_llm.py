#!/usr/bin/env python3
"""
Mock LLM Server 启动脚本

用法:
    uv run python scripts/start_mock_llm.py                    # 默认 18003 端口
    uv run python scripts/start_mock_llm.py --port 8001        # 自定义端口
    uv run python scripts/start_mock_llm.py --responses path/to/responses.json  # 加载自定义响应

功能:
    - 模拟 OpenAI 兼容的 LLM API，返回预定义响应
    - 支持 SSE 流式响应
    - 记录请求统计，可通过 HTTP API 查询
    - 支持加载自定义响应列表
"""

import argparse
import json
import time
import threading

import httpx
import uvicorn


def _load_responses_after_startup(
    base_url: str, responses_path: str, delay: float = 1.0
):
    """等待服务器启动后加载自定义响应。"""
    time.sleep(delay)
    try:
        # 读取响应文件
        with open(responses_path, "r", encoding="utf-8") as f:
            responses = json.load(f)

        if not isinstance(responses, list):
            print("\n  ❌ 响应文件格式错误: 必须是字符串数组", flush=True)
            return

        # 发送到服务器
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base_url}/test/set_responses",
                json=responses,
            )
            resp.raise_for_status()
            result = resp.json()
            print(
                f"\n  ✓ 响应加载成功: {result.get('response_count', 0)} 条响应",
                flush=True,
            )
    except FileNotFoundError:
        print(f"\n  ❌ 响应文件未找到: {responses_path}", flush=True)
    except json.JSONDecodeError as e:
        print(f"\n  ❌ 响应文件 JSON 解析失败: {e}", flush=True)
    except Exception as e:
        print(f"\n  ❌ 响应加载失败: {e}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="启动 Mock LLM Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 默认 18003 端口
  %(prog)s --port 8001              # 自定义端口
  %(prog)s --responses custom_responses.json  # 加载自定义响应

响应文件格式 (JSON 数组):
  [
    "第一次请求的响应文本，可以包含 do(...) 或 finish(...) 命令",
    "第二次请求的响应文本",
    "第三次请求的响应文本"
  ]

测试 API:
  http://localhost:18003/test/stats          # 获取请求统计
  http://localhost:18003/test/reset          # 重置请求计数
  POST http://localhost:18003/test/set_responses  # 设置自定义响应
        """,
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=18003,
        help="服务器端口 (默认: 18003)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--responses",
        "-r",
        type=str,
        help="自定义响应 JSON 文件路径 (可选)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="warning",
        help="日志级别 (默认: warning)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用自动重载（开发模式）",
    )

    args = parser.parse_args()

    # 导入并创建 app
    from tests.integration.device_agent.mock_llm_server import create_app

    app = create_app()

    # 构建服务器 URL
    server_url = f"http://localhost:{args.port}"

    print("=" * 60)
    print("  Mock LLM Server (OpenAI Compatible)")
    print("=" * 60)
    print(f"  地址: http://{args.host}:{args.port}")
    print(f"  日志: {args.log_level}")
    if args.responses:
        print(f"  响应: {args.responses} (启动后自动加载)")
    else:
        print("  响应: 使用默认响应 (美团消息点击场景)")
    print("=" * 60)
    print("\nAPI 端点:")
    print("  POST /v1/chat/completions         # OpenAI 兼容聊天接口")
    print("\n测试 API:")
    print("  GET  /test/stats                  # 请求统计")
    print("  POST /test/reset                  # 重置计数")
    print("  POST /test/set_responses          # 设置响应")
    print("=" * 60)
    print("\n使用示例:")
    print(f"  curl -X POST {server_url}/v1/chat/completions \\")
    print('    -H "Content-Type: application/json" \\')
    print(
        '    -d \'{"model": "mock-glm", "messages": [{"role": "user", "content": "test"}], "stream": true}\''
    )
    print("=" * 60)
    print()

    # 如果有自定义响应，启动后台线程在服务器启动后加载
    if args.responses:
        load_thread = threading.Thread(
            target=_load_responses_after_startup,
            args=(server_url, args.responses),
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
