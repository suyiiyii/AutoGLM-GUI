"""CLI entry point for AutoGLM-GUI."""

import argparse
import sys
import socket
import threading
import time
import webbrowser

from AutoGLM_GUI import __version__

# Default configuration
DEFAULT_MODEL_NAME = "autoglm-phone-9b"


def find_available_port(
    start_port: int = 8000, max_attempts: int = 100, host: str = "127.0.0.1"
) -> int:
    """Find an available port starting from start_port.

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try
        host: Host to bind to (default: 127.0.0.1)

    Returns:
        An available port number

    Raises:
        RuntimeError: If no available port found within max_attempts
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            # Try to bind to the port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            # Port is in use, try next one
            continue

    raise RuntimeError(
        f"Could not find available port in range {start_port}-{start_port + max_attempts - 1}"
    )


def open_browser(
    host: str, port: int, use_ssl: bool = False, delay: float = 1.5
) -> None:
    """Open browser after a delay to ensure server is ready.

    Args:
        host: Server host
        port: Server port
        use_ssl: Whether to use HTTPS
        delay: Delay in seconds before opening browser
    """

    def _open():
        time.sleep(delay)
        protocol = "https" if use_ssl else "http"
        url = (
            f"{protocol}://127.0.0.1:{port}"
            if host == "0.0.0.0"
            else f"{protocol}://{host}:{port}"
        )
        try:
            webbrowser.open(url)
        except Exception as e:
            # Non-critical failure, just log it
            print(f"Could not open browser automatically: {e}", file=sys.stderr)

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def main() -> None:
    """Start the AutoGLM-GUI server."""
    parser = argparse.ArgumentParser(
        description="AutoGLM-GUI - Web GUI for AutoGLM Phone Agent"
    )
    parser.add_argument(
        "--base-url",
        required=False,
        help="Base URL of the model API (e.g., http://localhost:8080/v1)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model name to use (default: {DEFAULT_MODEL_NAME}, or from config file)",
    )
    parser.add_argument(
        "--apikey",
        default=None,
        help="API key for the model API (default: from AUTOGLM_API_KEY or unset)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind the server to (default: auto-find starting from 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Console log level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default="logs/autoglm_{time:YYYY-MM-DD}.log",
        help="Log file path (default: logs/autoglm_{time:YYYY-MM-DD}.log)",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Disable file logging",
    )
    parser.add_argument(
        "--ssl-keyfile",
        default=None,
        help="SSL key file path (for HTTPS)",
    )
    parser.add_argument(
        "--ssl-certfile",
        default=None,
        help="SSL certificate file path (for HTTPS)",
    )

    args = parser.parse_args()

    # Auto-find available port if not specified
    if args.port is None:
        try:
            args.port = find_available_port(start_port=8000, host=args.host)
            print(f"\nAuto-detected available port: {args.port}\n")
        except RuntimeError as e:
            print(f"\nError: {e}", file=sys.stderr)
            sys.exit(1)

    import uvicorn

    from AutoGLM_GUI import server
    from AutoGLM_GUI.config_manager import config_manager
    from AutoGLM_GUI.logger import configure_logger

    # Configure logging system
    configure_logger(
        console_level=args.log_level,
        log_file=None if args.no_log_file else args.log_file,
    )

    # ==================== 配置系统初始化 ====================
    # 使用统一配置管理器（四层优先级：CLI > ENV > FILE > DEFAULT）

    # 1. 设置 CLI 参数配置（最高优先级）
    config_manager.set_cli_config(
        base_url=args.base_url, model_name=args.model, api_key=args.apikey
    )

    # 2. 加载环境变量配置
    config_manager.load_env_config()

    # 3. 加载配置文件
    config_manager.load_file_config()

    # 4. 获取合并后的有效配置
    effective_config = config_manager.get_effective_config()

    # 5. 同步到环境变量（reload 模式需要）
    config_manager.sync_to_env()

    # 获取配置来源
    config_source = config_manager.get_config_source()

    # Determine if SSL is enabled
    use_ssl = args.ssl_keyfile is not None and args.ssl_certfile is not None

    # Display startup banner
    print()
    print("=" * 50)
    print("  AutoGLM-GUI - Phone Agent Web Interface")
    print("=" * 50)
    print(f"  Version:    {__version__}")
    print()
    protocol = "https" if use_ssl else "http"
    print(f"  Server:     {protocol}://{args.host}:{args.port}")
    print()
    print("  Model Configuration:")
    print(f"    Source:   {config_source.value}")
    print(f"    Base URL: {effective_config.base_url or '(not set)'}")
    print(f"    Model:    {effective_config.model_name}")
    if effective_config.api_key != "EMPTY":
        print("    API Key:  (configured)")
    print()

    # Warning if base_url is not configured
    if not effective_config.base_url:
        print("  [!]  WARNING: base_url is not configured!")
        print("     Please configure via frontend or use --base-url")
        print()

    print("=" * 50)
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # Open browser automatically unless disabled
    if not args.no_browser:
        open_browser(args.host, args.port, use_ssl=use_ssl)

    uvicorn.run(
        server.app if not args.reload else "AutoGLM_GUI.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
    )


if __name__ == "__main__":
    main()
