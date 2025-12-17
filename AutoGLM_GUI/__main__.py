"""CLI entry point for AutoGLM-GUI."""

import argparse
import os
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


def open_browser(host: str, port: int, delay: float = 1.5) -> None:
    """Open browser after a delay to ensure server is ready.

    Args:
        host: Server host
        port: Server port
        delay: Delay in seconds before opening browser
    """

    def _open():
        time.sleep(delay)
        url = (
            f"http://127.0.0.1:{port}" if host == "0.0.0.0" else f"http://{host}:{port}"
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
        default=DEFAULT_MODEL_NAME,
        help=f"Model name to use (default: {DEFAULT_MODEL_NAME})",
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
    from AutoGLM_GUI.config import config
    from AutoGLM_GUI.config_manager import load_config_file, merge_configs
    from AutoGLM_GUI.logger import configure_logger

    # Configure logging system
    configure_logger(
        console_level=args.log_level,
        log_file=None if args.no_log_file else args.log_file,
    )

    # Load configuration from file
    file_config = load_config_file()

    # Build CLI config dictionary (only include provided arguments)
    cli_config = {}
    if args.base_url:
        cli_config["base_url"] = args.base_url
    if args.model:
        cli_config["model_name"] = args.model
    if args.apikey:
        cli_config["api_key"] = args.apikey

    # Merge configurations (CLI > file > defaults)
    merged_config = merge_configs(file_config, cli_config)

    # Set model configuration via environment variables (survives reload)
    os.environ["AUTOGLM_BASE_URL"] = merged_config["base_url"]
    os.environ["AUTOGLM_MODEL_NAME"] = merged_config["model_name"]
    os.environ["AUTOGLM_API_KEY"] = merged_config["api_key"]

    # Refresh config from environment variables
    config.refresh_from_env()

    # Determine configuration source
    config_source = "default"
    if cli_config:
        config_source = "CLI arguments"
    elif file_config:
        config_source = "config file (~/.config/autoglm/config.json)"

    # Display startup banner
    print()
    print("=" * 50)
    print("  AutoGLM-GUI - Phone Agent Web Interface")
    print("=" * 50)
    print(f"  Version:    {__version__}")
    print()
    print(f"  Server:     http://{args.host}:{args.port}")
    print()
    print("  Model Configuration:")
    print(f"    Source:   {config_source}")
    print(f"    Base URL: {merged_config['base_url'] or '(not set)'}")
    print(f"    Model:    {merged_config['model_name']}")
    if merged_config["api_key"] != "EMPTY":
        print("    API Key:  (configured)")
    print()

    # Warning if base_url is not configured
    if not merged_config["base_url"]:
        print("  [!]  WARNING: base_url is not configured!")
        print("     Please configure via frontend or use --base-url")
        print()

    print("=" * 50)
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # Open browser automatically unless disabled
    if not args.no_browser:
        open_browser(args.host, args.port)

    uvicorn.run(
        server.app if not args.reload else "AutoGLM_GUI.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
