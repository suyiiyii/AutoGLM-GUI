"""Layered agent execution service for task-backed orchestration."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents import Agent, Runner, SQLiteSession, function_tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from AutoGLM_GUI.config_manager import config_manager
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.trace import TraceSpan, summarize_text, trace_span

if TYPE_CHECKING:
    from agents.result import RunResultStreaming


PLANNER_INSTRUCTIONS = """## 核心目标
你是一个负责操控手机的高级智能中枢。你的任务是将用户的意图转化为**视觉模型（Vision Model）**可以执行的原子操作。

## ⚠️ 极其重要的限制：视觉模型的能力边界 (Must Read)
你的下级（Vision Model）是一个**纯粹的执行者和观察者**。
1. **无"记忆/笔记"功能**：它没有 `Note` 功能，无法为你保存数据。
2. **无"系统级"权限**：它不能复制源代码，不能直接提取文本，不能读取剪贴板。
3. **唯一的输出**：它只能通过**对话**告诉你它看到了什么，或者去**点击/滑动**屏幕。

## 交互策略 (Interaction Strategy)

### 1. 如果你需要"操作手机" (To Act)
下达明确的 UI 动作指令。
- ✅ "点击'设置'图标。"
- ✅ "向下滑动屏幕。"
- ✅ "打开微信。"

### 2. 如果你需要"获取信息" (To Read/Extract)
你必须通过**提问**的方式，让视觉模型在对话中把信息"念"给你听。
- ❌ **错误**: "把验证码保存下来。" (它做不到)
- ❌ **错误**: "使用 Note 功能记录价格。" (它没有这个功能)
- ✅ **正确**: 调用 `chat` 询问："请看屏幕，告诉我现在的订单总金额是多少？"
  - *结果*: 视觉模型会回复 "25.5元"。你需要自己处理这个文本信息。

### 3. 如果用户要求"复制/粘贴"
必须通过模拟手指操作来实现，不能直接操作剪贴板。
- ✅ **正确**: "长按这段文字，等待弹出菜单，然后点击'复制'按钮。"

## 任务拆解原则 (Decomposition Rules)

1. **原子化**: 每次只给一个动作。
2. **可视化**: 指令必须基于屏幕上**看得见**的元素。不要说"点击确认"，如果屏幕上显示的按钮叫"OK"，请说"点击'OK'按钮"。
3. **Fail Fast**: 如果视觉模型回复 `ELEMENT_NOT_FOUND`，不要死循环。询问它："那现在屏幕上有什么？"或者尝试滑动寻找。

## 核心工作流 (The Loop)
1. **Observe (看)**: 调用 `chat` 询问当前状态。
   - "现在屏幕上显示什么？" / "刚才的点击生效了吗？"
2. **Think (想)**:
   - 用户的目标是什么？
   - 我需要让视觉模型**做什么动作**，还是**回答什么问题**？
3. **Act (做)**:
   - **Case A (动作)**: 发送指令 `点击[坐标]...`
   - **Case B (询问)**: 发送问题 `请读取...`

## 工具集 (Tools)
1. `list_devices()`
2. `chat(device_id, message)`:
   - 发送操作指令（如"点击红色按钮"）。
   - 发送查询问题（如"那个验证码是多少？"）。
"""


class TracedSQLiteSession(SQLiteSession):
    """SQLiteSession wrapper that exposes planner memory operations as spans."""

    async def get_items(self, limit: int | None = None) -> list[Any]:
        with trace_span(
            "memory.read",
            attrs={
                "memory_type": "layered_session",
                "session_id": self.session_id,
                "limit": limit,
            },
        ) as span:
            items = await super().get_items(limit)
            span.set_attribute("item_count", len(items))
            return items

    async def add_items(self, items: list[Any]) -> None:
        with trace_span(
            "memory.write",
            attrs={
                "memory_type": "layered_session",
                "session_id": self.session_id,
                "item_count": len(items),
            },
        ):
            await super().add_items(items)

    async def pop_item(self) -> Any | None:
        with trace_span(
            "memory.delete",
            attrs={
                "memory_type": "layered_session",
                "session_id": self.session_id,
                "operation": "pop_item",
            },
        ) as span:
            item = await super().pop_item()
            span.set_attribute("deleted", item is not None)
            return item

    async def clear_session(self) -> None:
        with trace_span(
            "memory.clear",
            attrs={
                "memory_type": "layered_session",
                "session_id": self.session_id,
            },
        ):
            await super().clear_session()


_sessions: dict[str, TracedSQLiteSession] = {}
_active_runs: dict[str, "RunResultStreaming"] = {}
_active_runs_lock = threading.Lock()

_client: AsyncOpenAI | None = None
_agent: Agent[Any] | None = None
_cached_config_hash: str | None = None


def _get_or_create_session(session_id: str) -> SQLiteSession:
    if session_id not in _sessions:
        with trace_span(
            "memory.session.create",
            attrs={
                "memory_type": "layered_session",
                "session_id": session_id,
            },
        ):
            _sessions[session_id] = TracedSQLiteSession(session_id)
            logger.info(f"[LayeredAgent] Created new session: {session_id}")
    return _sessions[session_id]


def reset_session(session_id: str) -> bool:
    if session_id in _sessions:
        with trace_span(
            "memory.session.drop",
            attrs={
                "memory_type": "layered_session",
                "session_id": session_id,
            },
        ):
            del _sessions[session_id]
            logger.info(f"[LayeredAgent] Cleared session: {session_id}")
        return True
    return False


def get_planner_model() -> str:
    config_manager.load_file_config()
    effective_config = config_manager.get_effective_config()
    model_name = effective_config.decision_model_name

    if not model_name:
        raise ValueError(
            "决策模型未配置。使用分层代理模式需要配置决策模型。\n"
            "请在全局配置中设置决策模型的 Base URL、模型名称和 API Key。"
        )

    logger.info(f"[LayeredAgent] Using decision model: {model_name}")
    return model_name


def _setup_openai_client() -> AsyncOpenAI:
    config_manager.load_file_config()
    effective_config = config_manager.get_effective_config()

    decision_base_url = effective_config.decision_base_url
    decision_api_key = effective_config.decision_api_key

    if not decision_base_url:
        raise ValueError(
            "决策模型 Base URL 未配置。使用分层代理模式需要配置决策模型。\n"
            "请在全局配置中设置决策模型的 Base URL、模型名称和 API Key。"
        )

    planner_model = get_planner_model()

    logger.info("[LayeredAgent] Decision model config:")
    logger.info(f"  - Base URL: {decision_base_url}")
    logger.info(f"  - Model: {planner_model}")
    logger.info(f"  - API Key: {'***' if decision_api_key else 'None'}")

    return AsyncOpenAI(
        base_url=decision_base_url,
        api_key=decision_api_key or "EMPTY",
    )


@function_tool
async def list_devices() -> str:
    from AutoGLM_GUI.api.devices import _build_device_response_with_agent
    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    with trace_span("layered.tool.list_devices"):
        logger.info("[LayeredAgent] list_devices tool called")

        device_manager = DeviceManager.get_instance()
        agent_manager = PhoneAgentManager.get_instance()

        if not device_manager.is_polling_active():
            logger.warning("Polling not started, performing sync refresh")
            device_manager.force_refresh()

        managed_devices = device_manager.get_devices()
        devices_with_agents = [
            _build_device_response_with_agent(d, agent_manager) for d in managed_devices
        ]
        devices_dict = [device.model_dump() for device in devices_with_agents]
        return json.dumps(devices_dict, ensure_ascii=False, indent=2)


@function_tool
async def chat(device_id: str, message: str) -> str:
    from AutoGLM_GUI.exceptions import DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
    from AutoGLM_GUI.prompts import MCP_SYSTEM_PROMPT_ZH

    mcp_max_steps = 5

    with trace_span(
        "layered.tool.chat",
        attrs={
            "device_id": device_id,
            "task_preview": summarize_text(message) or "",
            "task_length": len(message),
        },
    ) as tool_span:
        logger.info(
            f"[LayeredAgent] chat tool called: device_id={device_id}, message={message}"
        )

        manager = PhoneAgentManager.get_instance()
        acquired = False

        try:
            with trace_span(
                "layered.tool.chat.acquire_device",
                attrs={"device_id": device_id},
            ):
                acquired = await manager.acquire_device_async(
                    device_id,
                    auto_initialize=True,
                    context="layered",
                )

            with trace_span(
                "layered.tool.chat.get_agent",
                attrs={"device_id": device_id},
            ):
                agent = await asyncio.to_thread(
                    manager.get_agent_with_context,
                    device_id,
                    context="layered",
                    agent_type=None,
                )

            original_max_steps = agent.agent_config.max_steps
            original_system_prompt = agent.agent_config.system_prompt

            agent.agent_config.max_steps = mcp_max_steps
            agent.agent_config.system_prompt = MCP_SYSTEM_PROMPT_ZH

            try:
                with trace_span(
                    "layered.tool.chat.reset_agent",
                    attrs={"device_id": device_id},
                ):
                    agent.reset()

                with trace_span(
                    "layered.tool.chat.run_agent",
                    attrs={
                        "device_id": device_id,
                        "agent_type": agent.__class__.__name__,
                        "is_async_agent": True,
                    },
                ):
                    result = await agent.run(message)
                steps = agent.step_count

                if steps >= mcp_max_steps and result == "Max steps reached":
                    tool_span.set_attributes(
                        {
                            "success": False,
                            "steps": mcp_max_steps,
                            "error_kind": "max_steps",
                        }
                    )
                    context_json = json.dumps(
                        agent.context, ensure_ascii=False, indent=2
                    )
                    return json.dumps(
                        {
                            "result": f"⚠️ 已达到最大步数限制（{mcp_max_steps}步）。视觉模型可能遇到了困难，任务未完成。\n\n执行历史:\n{context_json}\n\n建议: 请重新规划任务或将其拆分为更小的子任务。",
                            "steps": mcp_max_steps,
                            "success": False,
                        },
                        ensure_ascii=False,
                    )

                tool_span.set_attributes({"success": True, "steps": steps})
                return json.dumps(
                    {
                        "result": result,
                        "steps": steps,
                        "success": True,
                    },
                    ensure_ascii=False,
                )
            finally:
                agent.agent_config.max_steps = original_max_steps
                agent.agent_config.system_prompt = original_system_prompt
        except DeviceBusyError:
            tool_span.set_attributes({"success": False, "error_kind": "busy"})
            return json.dumps(
                {
                    "result": f"设备 {device_id} 正忙，请稍后再试。",
                    "steps": 0,
                    "success": False,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            tool_span.set_attributes({"success": False, "error_kind": "unexpected"})
            logger.error(f"[LayeredAgent] chat tool error: {exc}")
            return json.dumps(
                {
                    "result": str(exc),
                    "steps": 0,
                    "success": False,
                },
                ensure_ascii=False,
            )
        finally:
            if acquired:
                try:
                    with trace_span(
                        "layered.tool.chat.release_device",
                        attrs={"device_id": device_id},
                    ):
                        manager.release_device(device_id, context="layered")
                except BaseException as exc:  # pragma: no cover - safety net
                    logger.error(
                        f"Failed to release device lock for {device_id}: {exc}"
                    )


def _create_planner_agent(client: AsyncOpenAI) -> Agent[Any]:
    planner_model = get_planner_model()
    model = OpenAIChatCompletionsModel(
        model=planner_model,
        openai_client=client,
    )

    return Agent(
        name="Planner",
        instructions=PLANNER_INSTRUCTIONS,
        model=model,
        tools=[list_devices, chat],
    )


def _compute_config_hash() -> str:
    import hashlib

    config = config_manager.get_effective_config()
    config_str = config.model_dump_json()
    return hashlib.md5(config_str.encode()).hexdigest()


def _ensure_agent() -> Agent[Any]:
    global _client, _agent, _cached_config_hash

    current_hash = _compute_config_hash()

    if _agent is None or _cached_config_hash != current_hash:
        if _agent is not None and _cached_config_hash != current_hash:
            logger.info(
                f"[LayeredAgent] Config changed (hash: {_cached_config_hash} -> {current_hash}), reloading agent..."
            )

        _client = _setup_openai_client()
        _agent = _create_planner_agent(_client)
        _cached_config_hash = current_hash
        logger.info(
            f"[LayeredAgent] Agent initialized/reloaded with config hash: {current_hash}"
        )

    return _agent


@dataclass
class LayeredTaskRun:
    task_id: str
    session_id: str
    result: "RunResultStreaming"
    final_output: str = ""
    success: bool = False
    cancelled: bool = False
    finished: bool = False
    _current_tool_call: dict[str, Any] | None = field(default=None, init=False)

    def cancel(self) -> None:
        self.cancelled = True
        self.result.cancel(mode="immediate")

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent

        model_span: TraceSpan | None = None
        raw_event_count = 0

        def close_model_span() -> None:
            nonlocal model_span, raw_event_count
            if model_span is not None:
                model_span.__exit__(None, None, None)
                model_span = None
                raw_event_count = 0

        try:
            with trace_span(
                "layered.planner.stream",
                attrs={
                    "task_id": self.task_id,
                    "session_id": self.session_id,
                },
            ) as stream_span:
                async for event in self.result.stream_events():
                    if isinstance(event, RawResponsesStreamEvent):
                        if model_span is None:
                            model_span = trace_span(
                                "model.call",
                                attrs={
                                    "model_role": "layered_planner",
                                    "task_id": self.task_id,
                                    "session_id": self.session_id,
                                },
                            )
                            model_span.__enter__()
                        raw_event_count += 1
                        raw_data = getattr(event, "data", None)
                        raw_event_type = getattr(raw_data, "type", None)
                        model_span.set_attributes(
                            {
                                "raw_event_count": raw_event_count,
                                "last_raw_event_type": raw_event_type
                                or type(raw_data).__name__,
                            }
                        )
                        continue

                    close_model_span()
                    if not isinstance(event, RunItemStreamEvent):
                        continue

                    item = event.item
                    item_type = getattr(item, "type", None)

                    if item_type == "tool_call_item":
                        with trace_span(
                            "tool.call",
                            attrs={
                                "task_id": self.task_id,
                                "session_id": self.session_id,
                                "caller": "layered_planner",
                            },
                        ) as span:
                            event_payload = self._parse_tool_call(item)
                            tool_args = event_payload["tool_args"]
                            span.set_attributes(
                                {
                                    "tool_name": event_payload["tool_name"],
                                    "tool_arg_keys": sorted(tool_args.keys())
                                    if isinstance(tool_args, dict)
                                    else [],
                                    "tool_args_preview": summarize_text(
                                        json.dumps(
                                            tool_args,
                                            ensure_ascii=False,
                                            default=str,
                                        ),
                                        limit=512,
                                    ),
                                }
                            )
                            self._current_tool_call = {
                                "name": event_payload["tool_name"],
                                "args": event_payload["tool_args"],
                            }
                        yield {
                            "type": "tool_call",
                            "payload": event_payload,
                        }
                    elif item_type == "tool_call_output_item":
                        output = getattr(item, "output", "")
                        tool_name = (
                            self._current_tool_call["name"]
                            if self._current_tool_call
                            else "unknown"
                        )
                        with trace_span(
                            "tool.result",
                            attrs={
                                "task_id": self.task_id,
                                "session_id": self.session_id,
                                "caller": "layered_planner",
                                "tool_name": tool_name,
                            },
                        ) as span:
                            result_text, steps, sub_success = self._parse_tool_output(
                                output
                            )
                            span.set_attributes(
                                {
                                    "steps": steps,
                                    "success": sub_success,
                                    "result_preview": summarize_text(result_text, 512),
                                }
                            )
                            tool_result_payload: dict[str, Any] = {
                                "tool_name": tool_name,
                                "result": result_text,
                            }
                            if steps:
                                tool_result_payload["steps"] = steps
                            if sub_success is not None:
                                tool_result_payload["success"] = sub_success
                            self._current_tool_call = None
                        yield {
                            "type": "tool_result",
                            "payload": tool_result_payload,
                        }
                    elif item_type == "message_output_item":
                        with trace_span(
                            "layered.planner.message",
                            attrs={
                                "task_id": self.task_id,
                                "session_id": self.session_id,
                            },
                        ) as span:
                            content = self._extract_message_content(item)
                            span.set_attribute(
                                "content_preview",
                                summarize_text(content, 512),
                            )
                        if content:
                            yield {
                                "type": "message",
                                "payload": {"content": content},
                            }

                close_model_span()
                self.final_output = (
                    self.result.final_output
                    if hasattr(self.result, "final_output")
                    else ""
                )
                self.success = True
                stream_span.set_attributes(
                    {
                        "success": True,
                        "final_output_preview": summarize_text(
                            self.final_output,
                            512,
                        ),
                    }
                )
                yield {
                    "type": "done",
                    "payload": {
                        "content": self.final_output,
                        "success": True,
                    },
                }
        except asyncio.CancelledError:
            close_model_span()
            self.cancelled = True
            raise
        except Exception as exc:
            close_model_span()
            if self.cancelled:
                self.final_output = "Task cancelled by user"
                self.success = False
                yield {
                    "type": "cancelled",
                    "payload": {"message": self.final_output},
                }
            else:
                logger.exception(f"[LayeredAgent] Error: {exc}")
                self.final_output = str(exc)
                self.success = False
                yield {
                    "type": "error",
                    "payload": {"message": str(exc)},
                }
        finally:
            with _active_runs_lock:
                _active_runs.pop(self.task_id, None)
            self.finished = True

    @staticmethod
    def _parse_tool_output(output: Any) -> tuple[str, int, bool | None]:
        """Unpack a tool output into ``(text, steps, sub_success)``.

        The ``chat`` tool returns a JSON envelope ``{"result", "steps", "success"}``
        describing the inner phone-agent run.  Other tools (e.g. ``list_devices``)
        return plain strings, in which case ``steps`` is ``0`` and ``sub_success``
        is ``None``.
        """
        text = output if isinstance(output, str) else str(output)
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return text, 0, None
        if isinstance(parsed, dict) and "steps" in parsed:
            raw_steps = parsed.get("steps", 0)
            steps = int(raw_steps) if isinstance(raw_steps, (int, float)) else 0
            success = parsed.get("success")
            return text, steps, success if isinstance(success, bool) else None
        return text, 0, None

    def _parse_tool_call(self, item: Any) -> dict[str, Any]:
        tool_name = "unknown"
        tool_args: dict[str, Any] = {}

        if hasattr(item, "raw_item") and item.raw_item:
            raw = item.raw_item
            if isinstance(raw, dict):
                tool_name = raw.get(
                    "name", raw.get("function", {}).get("name", "unknown")
                )
                args_str = raw.get(
                    "arguments", raw.get("function", {}).get("arguments", "{}")
                )
                tool_args = self._parse_json_args(args_str)
            else:
                func = getattr(raw, "function", None)
                if func:
                    tool_name = getattr(func, "name", "unknown")
                    args_val = getattr(func, "arguments", None)
                    if args_val:
                        tool_args = self._parse_json_args(args_val)
                else:
                    name_val = getattr(raw, "name", None)
                    if name_val:
                        tool_name = name_val
                        args_val = getattr(raw, "arguments", None)
                        if args_val:
                            tool_args = self._parse_json_args(args_val)

        if tool_name == "unknown":
            if hasattr(item, "name") and item.name:
                tool_name = item.name
            elif hasattr(item, "call") and item.call:
                call = item.call
                if hasattr(call, "function") and call.function:
                    if hasattr(call.function, "name"):
                        tool_name = call.function.name
                    if hasattr(call.function, "arguments"):
                        tool_args = self._parse_json_args(call.function.arguments)
                elif hasattr(call, "name"):
                    tool_name = call.name
                    if hasattr(call, "arguments"):
                        tool_args = self._parse_json_args(call.arguments)

        logger.info(
            f"[LayeredAgent] Tool call: {tool_name}, args keys: {list(tool_args.keys())}"
        )
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
        }

    @staticmethod
    def _parse_json_args(args_val: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(args_val) if isinstance(args_val, str) else args_val
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except Exception:
            return {"raw": str(args_val)}

    @staticmethod
    def _extract_message_content(item: Any) -> str:
        content = ""
        raw_item = getattr(item, "raw_item", None)
        if raw_item:
            raw_content = getattr(raw_item, "content", None)
            if raw_content:
                for chunk in raw_content:
                    text_val = getattr(chunk, "text", None)
                    if text_val:
                        content += text_val
        return content


def start_run(
    *,
    task_id: str,
    session_id: str,
    message: str,
) -> LayeredTaskRun:
    agent = _ensure_agent()
    session = _get_or_create_session(session_id)
    effective_config = config_manager.get_effective_config()
    max_turns = effective_config.layered_max_turns
    resolved_max_turns = max_turns if max_turns is not None else 100000
    with trace_span(
        "layered.planner.run_streamed",
        attrs={
            "task_id": task_id,
            "session_id": session_id,
            "max_turns": resolved_max_turns,
            "message_preview": summarize_text(message, 512),
        },
    ):
        result = Runner.run_streamed(
            agent,
            message,
            max_turns=resolved_max_turns,
            session=session,
        )

    with _active_runs_lock:
        _active_runs[task_id] = result

    return LayeredTaskRun(
        task_id=task_id,
        session_id=session_id,
        result=result,
    )


def cancel_task(task_id: str) -> bool:
    with _active_runs_lock:
        result = _active_runs.get(task_id)
    if result is None:
        return False
    result.cancel(mode="immediate")
    logger.info(f"[LayeredAgent] Aborted task: {task_id}")
    return True
