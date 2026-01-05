"""
视觉小模型适配器

适配 autoglm-phone 等视觉模型，提供屏幕识别和动作执行能力
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from openai import OpenAI

from AutoGLM_GUI.actions.handler import ActionHandler
from AutoGLM_GUI.config import ModelConfig
from AutoGLM_GUI.device_manager import DeviceManager
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder
from AutoGLM_GUI.parsers import PhoneAgentParser

from .protocols import VISION_DESCRIBE_PROMPT


@dataclass
class ScreenDescription:
    """屏幕描述结果"""

    description: str  # 屏幕文字描述
    current_app: str  # 当前应用
    elements: list[str]  # 识别到的主要元素
    raw_response: str = ""


@dataclass
class ExecutionResult:
    """动作执行结果"""

    success: bool
    action_type: str  # 执行的动作类型
    target: str  # 目标描述
    position: Optional[tuple[int, int]] = None  # 点击位置(如果有)
    message: str = ""
    finished: bool = False


class VisionModel:
    """
    视觉小模型 - 负责屏幕识别和动作执行

    使用 autoglm-phone 等视觉模型，识别屏幕内容并执行具体操作。
    在双模型协作中，充当"眼睛"和"手"的角色。
    """

    def __init__(
        self,
        model_config: ModelConfig,
        device_id: str,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
        takeover_callback: Optional[Callable[[str], None]] = None,
    ):
        self.model_config = model_config
        self.device_id = device_id
        self.openai_client = OpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )
        self.parser = PhoneAgentParser()

        device_manager = DeviceManager.get_instance()
        self._device = device_manager.get_device_protocol(device_id)

        self.action_handler = ActionHandler(
            device=self._device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        logger.info(f"视觉小模型初始化: {model_config.model_name}, 设备: {device_id}")

    def _request(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        response = self.openai_client.chat.completions.create(
            messages=messages,  # type: ignore[arg-type]
            model=self.model_config.model_name,
            max_tokens=self.model_config.max_tokens,
            temperature=self.model_config.temperature,
            top_p=self.model_config.top_p,
            frequency_penalty=self.model_config.frequency_penalty,
            extra_body=self.model_config.extra_body,
            stream=False,
        )

        raw_content = response.choices[0].message.content or ""

        thinking = ""
        action = ""

        if "<think>" in raw_content and "</think>" in raw_content:
            start = raw_content.find("<think>") + len("<think>")
            end = raw_content.find("</think>")
            thinking = raw_content[start:end].strip()

        if "<answer>" in raw_content and "</answer>" in raw_content:
            start = raw_content.find("<answer>") + len("<answer>")
            end = raw_content.find("</answer>")
            action = raw_content[start:end].strip()
        elif "<answer>" in raw_content:
            start = raw_content.find("<answer>") + len("<answer>")
            action = raw_content[start:].strip()
        else:
            lines = raw_content.strip().split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("do(") or line.startswith("finish("):
                    action = line
                    break
            if not action:
                action = raw_content

        return thinking, action

    def capture_screenshot(self) -> tuple[str, int, int]:
        """
        截取当前屏幕

        Returns:
            (base64_string, width, height)
        """
        logger.debug("正在截取屏幕...")

        screenshot = self._device.get_screenshot()

        logger.debug(f"截图完成: {screenshot.width}x{screenshot.height}")
        return (
            screenshot.base64_data,
            screenshot.width,
            screenshot.height,
        )

    def describe_screen(
        self,
        screenshot_base64: Optional[str] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
    ) -> ScreenDescription:
        """
        识别并描述屏幕内容

        让视觉模型描述当前屏幕，生成文字描述供决策大模型使用。

        Args:
            screenshot_base64: 可选的截图base64，不提供则自动截取
            on_thinking: 思考过程回调

        Returns:
            ScreenDescription: 屏幕描述结果
        """
        logger.info("正在识别屏幕内容...")

        # 获取截图
        if screenshot_base64 is None:
            screenshot_base64, width, height = self.capture_screenshot()

        # 获取当前应用
        current_app = self._device.get_current_app()

        # 构建消息，要求模型描述屏幕
        messages = [
            MessageBuilder.create_system_message(
                "你是一个屏幕内容识别助手。请详细描述屏幕内容，帮助另一个AI做出操作决策。"
            ),
            MessageBuilder.create_user_message(
                text=f"""请描述这个屏幕的内容。

当前应用: {current_app}

{VISION_DESCRIBE_PROMPT}

请以结构化的方式描述屏幕内容。""",
                image_base64=screenshot_base64,
            ),
        ]

        # 调用视觉模型
        try:
            thinking, action = self._request(messages)

            # 解析描述
            description = thinking if thinking else action

            # 提取元素列表（简单解析）
            elements = self._extract_elements(description)

            result = ScreenDescription(
                description=description,
                current_app=current_app,
                elements=elements,
                raw_response=f"{thinking}\n{action}",
            )

            logger.info(f"屏幕识别完成: {current_app}, 识别到 {len(elements)} 个元素")
            return result

        except Exception as e:
            logger.error(f"屏幕识别失败: {e}")
            # 返回基础描述
            return ScreenDescription(
                description=f"当前应用: {current_app}，屏幕识别失败: {e}",
                current_app=current_app,
                elements=[],
            )

    def execute_decision(
        self,
        decision: dict,
        screenshot_base64: Optional[str] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """
        根据大模型的决策执行操作

        将大模型的高级决策转换为具体的屏幕操作。

        Args:
            decision: 大模型的决策，包含 action, target, content 等
            screenshot_base64: 当前截图(用于定位元素)
            on_thinking: 思考过程回调

        Returns:
            ExecutionResult: 执行结果
        """
        action_type = decision.get("action", "")
        target = decision.get("target", "")
        content = decision.get("content")

        logger.info(f"执行决策: {action_type} -> {target}")

        # 获取截图和尺寸
        if screenshot_base64 is None:
            screenshot_base64, width, height = self.capture_screenshot()
        else:
            screenshot = self._device.get_screenshot()
            width, height = screenshot.width, screenshot.height

        # 处理完成动作
        if action_type == "finish":
            return ExecutionResult(
                success=True,
                action_type="finish",
                target="",
                message=decision.get("reasoning", "任务完成"),
                finished=True,
            )

        # 对于需要定位的操作，调用视觉模型找到具体位置
        if action_type in ["tap", "swipe", "long_press", "double_tap"]:
            position = self._find_element_position(
                target, screenshot_base64, width, height, on_thinking
            )

            if position is None:
                return ExecutionResult(
                    success=False,
                    action_type=action_type,
                    target=target,
                    message=f"无法定位元素: {target}",
                )

            # 执行点击操作
            if action_type == "tap":
                action_dict = {
                    "_metadata": "do",
                    "action": "Tap",
                    "element": list(position),
                }
            elif action_type == "double_tap":
                action_dict = {
                    "_metadata": "do",
                    "action": "Double Tap",
                    "element": list(position),
                }
            elif action_type == "long_press":
                action_dict = {
                    "_metadata": "do",
                    "action": "Long Press",
                    "element": list(position),
                }
            else:
                action_dict = {
                    "_metadata": "do",
                    "action": "Tap",
                    "element": list(position),
                }

            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type=action_type,
                target=target,
                position=(
                    int(position[0] * width / 1000),
                    int(position[1] * height / 1000),
                ),
                message=result.message or "",
                finished=result.should_finish,
            )

        # 处理输入操作
        elif action_type == "type":
            if not content:
                return ExecutionResult(
                    success=False,
                    action_type="type",
                    target=target,
                    message="输入内容为空",
                )

            action_dict = {
                "_metadata": "do",
                "action": "Type",
                "text": content,
            }
            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type="type",
                target=target,
                message=f"输入: {content[:50]}..."
                if len(content) > 50
                else f"输入: {content}",
            )

        # 处理滑动操作
        elif action_type == "scroll":
            direction = decision.get("direction", "up")
            # 根据方向计算滑动坐标
            if direction == "up":
                start = [500, 700]
                end = [500, 300]
            elif direction == "down":
                start = [500, 300]
                end = [500, 700]
            elif direction == "left":
                start = [700, 500]
                end = [300, 500]
            else:  # right
                start = [300, 500]
                end = [700, 500]

            action_dict = {
                "_metadata": "do",
                "action": "Swipe",
                "start": start,
                "end": end,
            }
            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type="scroll",
                target=f"滚动{direction}",
            )

        # 处理返回操作
        elif action_type == "back":
            action_dict = {"_metadata": "do", "action": "Back"}
            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type="back",
                target="返回",
            )

        # 处理Home键
        elif action_type == "home":
            action_dict = {"_metadata": "do", "action": "Home"}
            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type="home",
                target="主页",
            )

        # 处理启动应用
        elif action_type == "launch":
            app_name = target or decision.get("app", "")
            action_dict = {
                "_metadata": "do",
                "action": "Launch",
                "app": app_name,
            }
            result = self.action_handler.execute(action_dict, width, height)

            return ExecutionResult(
                success=result.success,
                action_type="launch",
                target=app_name,
                message=result.message or "",
            )

        else:
            logger.warning(f"未知的动作类型: {action_type}")
            return ExecutionResult(
                success=False,
                action_type=action_type,
                target=target,
                message=f"未知的动作类型: {action_type}",
            )

    def _find_element_position(
        self,
        target_description: str,
        screenshot_base64: str,
        _width: int,
        _height: int,
        _on_thinking: Optional[Callable[[str], None]] = None,
    ) -> Optional[tuple[int, int]]:
        """
        使用视觉模型定位元素

        Args:
            target_description: 目标元素描述
            screenshot_base64: 截图base64
            width: 屏幕宽度
            height: 屏幕高度
            on_thinking: 思考过程回调

        Returns:
            (x, y) 归一化坐标(0-1000)，或 None
        """
        logger.debug(f"正在定位元素: {target_description}")

        # 构建定位请求
        messages = [
            MessageBuilder.create_system_message(
                """你是一个屏幕元素定位助手。根据用户描述的目标元素，找到它在屏幕上的位置。

请以以下格式返回:
do(action="Tap", element=[x, y])

其中 x 和 y 是 0-1000 范围的归一化坐标。
- x=0 表示最左边，x=1000 表示最右边
- y=0 表示最上边，y=1000 表示最下边

只返回坐标，不要其他解释。"""
            ),
            MessageBuilder.create_user_message(
                text=f"请找到并点击: {target_description}",
                image_base64=screenshot_base64,
            ),
        ]

        try:
            thinking, action_str = self._request(messages)

            action = self.parser.parse(action_str)

            if action.get("_metadata") == "do" and "element" in action:
                element = action["element"]
                if isinstance(element, list) and len(element) >= 2:
                    x, y = int(element[0]), int(element[1])
                    logger.info(f"元素定位成功: ({x}, {y})")
                    return (x, y)

            logger.warning(f"无法从响应中解析坐标: {action_str}")
            return None

        except Exception as e:
            logger.error(f"元素定位失败: {e}")
            return None

    def _extract_elements(self, description: str) -> list[str]:
        """从描述中提取主要元素列表"""
        elements = []

        # 简单的关键词提取
        keywords = ["按钮", "图标", "文本", "输入框", "搜索", "导航", "菜单", "列表"]
        lines = description.split("\n")

        for line in lines:
            line = line.strip()
            if any(kw in line for kw in keywords):
                # 清理并添加
                if len(line) < 100:  # 避免太长的描述
                    elements.append(line)

        return elements[:10]  # 最多返回10个元素

    def get_current_app(self) -> str:
        """获取当前应用"""
        return self._device.get_current_app()
