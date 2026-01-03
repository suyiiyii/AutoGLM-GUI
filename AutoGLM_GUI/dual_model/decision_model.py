"""
决策大模型客户端

调用 GLM-4.7 进行任务分析和决策
"""

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

from openai import OpenAI

from AutoGLM_GUI.logger import logger
from .protocols import (
    DecisionModelConfig,
    DECISION_SYSTEM_PROMPT,
    DECISION_SYSTEM_PROMPT_FAST,
    DECISION_SYSTEM_PROMPT_TURBO,
    DECISION_REPLAN_PROMPT,
    DECISION_HUMANIZE_PROMPT,
    ThinkingMode,
)


@dataclass
class TaskPlan:
    """任务计划"""

    summary: str
    steps: list[str]
    estimated_actions: int
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "steps": self.steps,
            "estimated_actions": self.estimated_actions,
        }


@dataclass
class ActionStep:
    """单个操作步骤"""

    action: str
    target: str = ""
    content: Optional[str] = None
    need_generate: bool = False
    direction: Optional[str] = None

    def to_dict(self) -> dict[str, str | bool]:
        result: dict[str, str | bool] = {"action": self.action, "target": self.target}
        if self.content:
            result["content"] = self.content
        if self.need_generate:
            result["need_generate"] = True
        if self.direction:
            result["direction"] = self.direction
        return result


@dataclass
class ActionSequence:
    """操作序列（TURBO模式）"""

    summary: str
    actions: list[ActionStep]
    checkpoints: list[str] = field(default_factory=list)
    humanize_steps: list[int] = field(default_factory=list)
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "actions": [a.to_dict() for a in self.actions],
            "checkpoints": self.checkpoints,
            "humanize_steps": self.humanize_steps,
        }

    def to_plan(self) -> TaskPlan:
        """转换为 TaskPlan 以保持兼容性"""
        return TaskPlan(
            summary=self.summary,
            steps=[f"{a.action}: {a.target}" for a in self.actions],
            estimated_actions=len(self.actions),
            raw_response=self.raw_response,
        )


@dataclass
class Decision:
    """决策结果"""

    action: str  # tap, swipe, type, scroll, back, home, launch
    target: str  # 目标描述
    reasoning: str  # 决策理由
    content: Optional[str] = None  # 输入内容(type操作时使用)
    finished: bool = False
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "target": self.target,
            "reasoning": self.reasoning,
            "content": self.content,
            "finished": self.finished,
        }


class DecisionModel:
    """
    决策大模型 - 负责任务分析和决策制定

    使用 GLM-4.7 或其他高智商模型，通过文本理解屏幕状态，
    制定操作决策并指导小模型执行。
    """

    def __init__(
        self,
        config: DecisionModelConfig,
        thinking_mode: ThinkingMode = ThinkingMode.DEEP,
    ):
        self.config = config
        self.thinking_mode = thinking_mode
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )  # type: ignore[call-arg]
        self.model_name = config.model_name
        self.conversation_history: list[dict] = []
        self.current_task: str = ""

        if thinking_mode == ThinkingMode.TURBO:
            self.system_prompt = DECISION_SYSTEM_PROMPT_TURBO
        elif thinking_mode == ThinkingMode.FAST:
            self.system_prompt = DECISION_SYSTEM_PROMPT_FAST
        else:
            self.system_prompt = DECISION_SYSTEM_PROMPT

        logger.info(
            f"决策大模型初始化: {config.model_name}, 模式: {thinking_mode.value}"
        )

    def _stream_completion(
        self,
        messages: list[dict],
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        流式调用大模型

        GLM-4.7 支持 reasoning_content 字段，可以分离思考过程和最终答案
        """
        logger.debug(f"调用决策大模型，消息数: {len(messages)}")

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=True,
            )

            full_reasoning = ""
            full_answer = ""
            done_reasoning = False

            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # 处理思考过程 (reasoning_content)
                    reasoning_chunk = getattr(delta, "reasoning_content", None) or ""
                    if reasoning_chunk:
                        full_reasoning += reasoning_chunk
                        if on_thinking:
                            on_thinking(reasoning_chunk)

                    # 处理最终答案 (content)
                    answer_chunk = delta.content or ""
                    if answer_chunk:
                        if not done_reasoning and full_reasoning:
                            done_reasoning = True
                            logger.debug("思考阶段结束，开始输出答案")

                        full_answer += answer_chunk
                        if on_answer:
                            on_answer(answer_chunk)

            # 如果模型不支持 reasoning_content，整个响应都在 content 中
            if not full_answer and full_reasoning:
                full_answer = full_reasoning
                full_reasoning = ""

            logger.debug(f"大模型响应完成，答案长度: {len(full_answer)}")
            return full_answer

        except Exception as e:
            logger.error(f"决策大模型调用失败: {e}")
            raise

    def analyze_task(
        self,
        task: str,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> TaskPlan:
        """
        分析用户任务，制定执行计划

        Args:
            task: 用户任务描述
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            TaskPlan: 任务执行计划
        """
        logger.info(f"分析任务: {task[:50]}... (模式: {self.thinking_mode.value})")

        # 构建消息（使用动态提示词）
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": f"""请分析以下任务，并制定执行计划：

任务: {task}

请以JSON格式返回任务计划。""",
            },
        ]

        # 调用模型
        response = self._stream_completion(messages, on_thinking, on_answer)

        # 解析响应
        try:
            # 尝试提取JSON
            plan_data = self._extract_json(response)

            if plan_data.get("type") == "plan":
                plan = TaskPlan(
                    summary=plan_data.get("summary", task),
                    steps=plan_data.get("steps", []),
                    estimated_actions=plan_data.get("estimated_actions", 5),
                    raw_response=response,
                )
            else:
                # 回退处理
                plan = TaskPlan(
                    summary=task,
                    steps=[task],
                    estimated_actions=5,
                    raw_response=response,
                )
        except Exception as e:
            logger.warning(f"解析任务计划失败: {e}")
            plan = TaskPlan(
                summary=task,
                steps=[task],
                estimated_actions=5,
                raw_response=response,
            )

        # 初始化对话历史（使用动态提示词）
        self.conversation_history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"任务: {task}"},
            {"role": "assistant", "content": response},
        ]

        logger.info(f"任务计划: {plan.summary}, 预计 {plan.estimated_actions} 步")
        return plan

    def analyze_task_turbo(
        self,
        task: str,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> ActionSequence:
        """
        TURBO模式：分析任务并生成完整操作序列

        一次性生成所有操作步骤，视觉模型直接执行，只有异常时才重新调用。

        Args:
            task: 用户任务描述
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            ActionSequence: 操作序列
        """
        logger.info(f"[TURBO] 分析任务: {task[:50]}...")
        self.current_task = task

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"任务: {task}\n\n请生成完整的操作序列。"},
        ]

        response = self._stream_completion(messages, on_thinking, on_answer)

        try:
            data = self._extract_json(response)

            if data.get("type") == "action_sequence":
                actions = []
                for a in data.get("actions", []):
                    actions.append(
                        ActionStep(
                            action=a.get("action", "tap"),
                            target=a.get("target", ""),
                            content=a.get("content"),
                            need_generate=a.get("need_generate", False),
                            direction=a.get("direction"),
                        )
                    )

                sequence = ActionSequence(
                    summary=data.get("summary", task),
                    actions=actions,
                    checkpoints=data.get("checkpoints", []),
                    humanize_steps=data.get("humanize_steps", []),
                    raw_response=response,
                )
            else:
                sequence = ActionSequence(
                    summary=task,
                    actions=[ActionStep(action="tap", target="未知")],
                    raw_response=response,
                )
        except Exception as e:
            logger.warning(f"[TURBO] 解析操作序列失败: {e}")
            sequence = ActionSequence(
                summary=task,
                actions=[ActionStep(action="tap", target="未知")],
                raw_response=response,
            )

        self.conversation_history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"任务: {task}"},
            {"role": "assistant", "content": response},
        ]

        logger.info(f"[TURBO] 生成 {len(sequence.actions)} 个操作步骤")
        return sequence

    def replan(
        self,
        current_state: str,
        executed_actions: list[str],
        error_info: str,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> ActionSequence:
        """
        TURBO模式：遇到问题时重新规划

        Args:
            current_state: 当前屏幕状态描述
            executed_actions: 已执行的操作列表
            error_info: 错误信息
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            ActionSequence: 新的操作序列
        """
        logger.info(f"[TURBO] 重新规划，错误: {error_info[:50]}...")

        prompt = DECISION_REPLAN_PROMPT.format(
            current_state=current_state,
            executed_actions="\n".join([f"- {a}" for a in executed_actions]),
            error_info=error_info,
        )

        self.conversation_history.append({"role": "user", "content": prompt})
        response = self._stream_completion(
            self.conversation_history, on_thinking, on_answer
        )
        self.conversation_history.append({"role": "assistant", "content": response})

        try:
            data = self._extract_json(response)
            actions = []
            for a in data.get("actions", []):
                actions.append(
                    ActionStep(
                        action=a.get("action", "tap"),
                        target=a.get("target", ""),
                        content=a.get("content"),
                        need_generate=a.get("need_generate", False),
                        direction=a.get("direction"),
                    )
                )

            return ActionSequence(
                summary=data.get("summary", "重新规划"),
                actions=actions,
                checkpoints=data.get("checkpoints", []),
                humanize_steps=data.get("humanize_steps", []),
                raw_response=response,
            )
        except Exception as e:
            logger.warning(f"[TURBO] 解析重规划失败: {e}")
            return ActionSequence(
                summary="重新规划失败",
                actions=[],
                raw_response=response,
            )

    def generate_humanize_content(
        self,
        task_context: str,
        current_scene: str,
        content_type: str,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        生成人性化内容（回复、评论、帖子等）

        Args:
            task_context: 任务背景
            current_scene: 当前场景描述
            content_type: 内容类型
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            str: 生成的内容
        """
        logger.info(f"[TURBO] 生成人性化内容: {content_type}")

        prompt = DECISION_HUMANIZE_PROMPT.format(
            task_context=task_context,
            current_scene=current_scene,
            content_type=content_type,
        )

        messages = [
            {
                "role": "system",
                "content": "你是一个社交媒体内容创作专家，擅长生成自然、真实、有个性的内容。",
            },
            {"role": "user", "content": prompt},
        ]

        content = self._stream_completion(messages, on_thinking, on_answer)
        content = content.strip()
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]

        logger.info(f"[TURBO] 生成内容长度: {len(content)}")
        return content

    def make_decision(
        self,
        screen_description: str,
        task_context: Optional[str] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> Decision:
        """
        根据屏幕描述做出决策

        Args:
            screen_description: 小模型提供的屏幕描述
            task_context: 额外的任务上下文
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            Decision: 决策结果
        """
        logger.info("正在做决策...")

        # 构建消息
        user_message = f"""当前屏幕状态：
{screen_description}

{f"补充信息: {task_context}" if task_context else ""}

请根据屏幕状态，决定下一步操作。以JSON格式返回决策。"""

        self.conversation_history.append({"role": "user", "content": user_message})

        # 调用模型
        response = self._stream_completion(
            self.conversation_history,
            on_thinking,
            on_answer,
        )

        # 保存助手响应
        self.conversation_history.append({"role": "assistant", "content": response})

        # 解析决策
        try:
            decision_data = self._extract_json(response)

            if decision_data.get("type") == "finish":
                decision = Decision(
                    action="finish",
                    target="",
                    reasoning=decision_data.get("message", "任务完成"),
                    finished=True,
                    raw_response=response,
                )
            elif decision_data.get("type") == "decision":
                decision = Decision(
                    action=decision_data.get("action", "tap"),
                    target=decision_data.get("target", ""),
                    reasoning=decision_data.get("reasoning", ""),
                    content=decision_data.get("content"),
                    finished=decision_data.get("finished", False),
                    raw_response=response,
                )
            else:
                # 尝试直接解析为决策
                decision = Decision(
                    action=decision_data.get("action", "tap"),
                    target=decision_data.get("target", "未知目标"),
                    reasoning=decision_data.get("reasoning", response),
                    content=decision_data.get("content"),
                    finished=decision_data.get("finished", False),
                    raw_response=response,
                )
        except Exception as e:
            logger.warning(f"解析决策失败: {e}")
            # 回退：将整个响应作为reasoning
            decision = Decision(
                action="unknown",
                target="",
                reasoning=response,
                raw_response=response,
            )

        logger.info(f"决策: {decision.action} -> {decision.target}")
        return decision

    def generate_content(
        self,
        content_type: str,
        context: str,
        requirements: Optional[str] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_answer: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        生成需要输入的内容（帖子、回复、消息等）

        Args:
            content_type: 内容类型（post, reply, message等）
            context: 上下文信息
            requirements: 具体要求
            on_thinking: 思考过程回调
            on_answer: 答案输出回调

        Returns:
            str: 生成的内容
        """
        logger.info(f"生成内容: {content_type}")

        prompt = f"""请为以下场景生成内容：

内容类型: {content_type}
上下文: {context}
{f"具体要求: {requirements}" if requirements else ""}

请直接返回生成的内容文本，不需要JSON格式，不需要额外解释。"""

        messages = [
            {
                "role": "system",
                "content": "你是一个内容创作助手，擅长生成各类社交媒体内容。请直接返回内容，不要添加任何解释或格式标记。",
            },
            {"role": "user", "content": prompt},
        ]

        content = self._stream_completion(messages, on_thinking, on_answer)

        # 清理内容（移除可能的引号和格式标记）
        content = content.strip()
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
        if content.startswith("```") and content.endswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        logger.info(f"生成内容完成，长度: {len(content)}")
        return content

    def _extract_json(self, text: str) -> dict:
        """从文本中提取JSON"""
        import re

        # 清理文本
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 ``` ... ``` 代码块（不带json标记）
        code_match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { 并匹配到对应的 }
        start_idx = text.find("{")
        if start_idx != -1:
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(text)):
                if text[i] == "{":
                    brace_count += 1
                elif text[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break

            if end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        # 最后尝试用非贪婪正则提取
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法从文本中提取JSON: {text[:100]}...")

    def reset(self):
        """重置对话历史"""
        self.conversation_history = []
        logger.info("决策大模型对话历史已重置")
