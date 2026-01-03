"""MCP (Model Context Protocol) tools for AutoGLM-GUI."""

from typing_extensions import TypedDict

from fastmcp import FastMCP

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.prompts import MCP_SYSTEM_PROMPT_ZH
from AutoGLM_GUI.schemas import DeviceResponse


class ChatResult(TypedDict):
    result: str
    steps: int
    success: bool


# 创建 MCP 服务器实例
mcp = FastMCP("AutoGLM-GUI MCP Server")

# MCP-specific step limit
MCP_MAX_STEPS = 5


@mcp.tool()
def chat(device_id: str, message: str) -> ChatResult:
    """
    Send a task to the AutoGLM Phone Agent for execution.

    The agent will be automatically initialized with global configuration
    if not already initialized. MCP calls use a specialized Fail-Fast prompt
    optimized for atomic operations within 5 steps.

    Args:
        device_id: Device identifier (e.g., "192.168.1.100:5555" or serial)
        message: Natural language task (e.g., "打开微信", "发送消息")
    """
    from AutoGLM_GUI.exceptions import DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    logger.info(f"[MCP] chat tool called: device_id={device_id}")

    manager = PhoneAgentManager.get_instance()

    # 使用上下文管理器获取 agent（自动管理锁，自动初始化）
    try:
        with manager.use_agent(device_id, timeout=None) as agent:
            # Temporarily override config for MCP (thread-safe within device lock)
            original_max_steps = agent.agent_config.max_steps
            original_system_prompt = agent.agent_config.system_prompt

            agent.agent_config.max_steps = MCP_MAX_STEPS
            agent.agent_config.system_prompt = MCP_SYSTEM_PROMPT_ZH

            try:
                # Reset agent before each chat to ensure clean state
                agent.reset()

                result = agent.run(message)
                steps = agent.step_count

                # Check if MCP step limit was reached
                if steps >= MCP_MAX_STEPS and result == "Max steps reached":
                    return {
                        "result": (
                            f"已达到 MCP 最大步数限制（{MCP_MAX_STEPS}步）。任务可能未完成，"
                            "建议将任务拆分为更小的子任务。"
                        ),
                        "steps": MCP_MAX_STEPS,
                        "success": False,
                    }

                return {"result": result, "steps": steps, "success": True}

            finally:
                # Restore original config
                agent.agent_config.max_steps = original_max_steps
                agent.agent_config.system_prompt = original_system_prompt

    except DeviceBusyError:
        raise RuntimeError(f"Device {device_id} is busy. Please wait.")
    except Exception as e:
        logger.error(f"[MCP] chat tool error: {e}")
        return {"result": str(e), "steps": 0, "success": False}


@mcp.tool()
def list_devices() -> list[DeviceResponse]:
    """
    List all connected ADB devices and their agent status.

    Returns:
        List of devices, each containing:
        - id: Device identifier for API calls
        - serial: Hardware serial number
        - model: Device model name
        - status: Connection status
        - connection_type: "usb" | "wifi" | "remote"
        - state: "online" | "offline" | "disconnected"
        - agent: Agent status (if initialized)
    """
    from AutoGLM_GUI.api.devices import _build_device_response_with_agent
    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    logger.info("[MCP] list_devices tool called")

    device_manager = DeviceManager.get_instance()
    agent_manager = PhoneAgentManager.get_instance()

    # Fallback: 如果轮询未启动，执行同步刷新
    if not device_manager._poll_thread or not device_manager._poll_thread.is_alive():
        logger.warning("Polling not started, performing sync refresh")
        device_manager.force_refresh()

    managed_devices = device_manager.get_devices()

    # 重用现有的聚合逻辑
    devices_with_agents = [
        _build_device_response_with_agent(d, agent_manager) for d in managed_devices
    ]

    return devices_with_agents


def get_mcp_asgi_app():
    """
    Get the MCP server's ASGI app for mounting in FastAPI.

    Returns:
        ASGI app that handles MCP protocol requests
    """
    # 创建 MCP HTTP app with /mcp path prefix
    # This will create routes under /mcp when mounted at root
    return mcp.http_app(path="/mcp")
