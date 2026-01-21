"""Custom exceptions for AutoGLM-GUI."""


class DeviceNotAvailableError(Exception):
    """Raised when device is not available (disconnected/offline)."""

    pass


class AgentNotInitializedError(Exception):
    """Raised when attempting to access an uninitialized agent without auto-initialization.

    This indicates that initialize_agent() must be called before the operation,
    OR that auto_initialize=True should be used in the calling method.

    Common scenarios:
        - Calling use_agent(device_id, auto_initialize=False) without prior init
        - Directly calling acquire_device() without prior init
        - Calling get_agent() with auto_initialize=False

    How to fix:
        Option 1 (Recommended): Use auto-initializing API
            >>> with manager.use_agent(device_id) as agent:  # auto_initialize=True
            >>>     result = agent.run("Open WeChat")

        Option 2: Explicitly initialize first
            >>> manager.initialize_agent(device_id, model_config, agent_config)
            >>> with manager.use_agent(device_id, auto_initialize=False) as agent:
            >>>     result = agent.run("Open WeChat")

        Option 3: Call /api/init endpoint (for REST API)
            >>> POST /api/init {"device_id": "...", "model_config": {...}, "agent_config": {...}}
    """

    pass


class DeviceBusyError(Exception):
    """Raised when device is currently processing a request.

    This indicates that another operation is currently using the device.
    Wait for the current operation to complete or use non-blocking mode.

    How to handle:
        Blocking mode (default):
            >>> with manager.use_agent(device_id) as agent:  # Waits until available
            >>>     result = agent.run("Open WeChat")

        Non-blocking mode:
            >>> try:
            >>>     with manager.use_agent(device_id, timeout=0) as agent:
            >>>         result = agent.run("Open WeChat")
            >>> except DeviceBusyError:
            >>>     print("Device is busy, try again later")

        Timeout mode:
            >>> try:
            >>>     with manager.use_agent(device_id, timeout=5.0) as agent:
            >>>         result = agent.run("Open WeChat")
            >>> except DeviceBusyError:
            >>>     print("Device still busy after 5 seconds")
    """

    pass


class AgentInitializationError(Exception):
    """Raised when agent initialization fails.

    This indicates a configuration error or runtime error during PhoneAgent construction.

    Common causes:
        - base_url not configured (check ~/.config/autoglm/config.json)
        - Invalid API key
        - Network connectivity issues
        - Device not connected via ADB
        - Missing or invalid model configuration

    How to fix:
        1. Check configuration:
            >>> from AutoGLM_GUI.config_manager import config_manager
            >>> effective_config = config_manager.get_effective_config()
            >>> print(f"base_url: {effective_config.base_url}")
            >>> print(f"model_name: {effective_config.model_name}")

        2. Set configuration:
            >>> via API: POST /api/config {"base_url": "...", "model_name": "...", "api_key": "..."}
            >>> via file: ~/.config/autoglm/config.json
            >>> via CLI: --base-url ... --model ... --apikey ...

        3. Verify device connection:
            $ adb devices

        4. Check error message for specific details
    """

    pass
