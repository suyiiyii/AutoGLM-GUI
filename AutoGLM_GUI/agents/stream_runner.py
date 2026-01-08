import queue
import threading
import typing
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from AutoGLM_GUI.agents.events import AgentEvent, AgentEventType

if typing.TYPE_CHECKING:
    from AutoGLM_GUI.agents.protocols import BaseAgent


class AgentStepStreamer:
    """
    流式 Agent 执行器（抽取可复用逻辑）.

    职责：
    - 管理事件队列
    - 协调 worker 线程
    - 转换 StepResult 为事件
    """

    def __init__(
        self,
        agent: "BaseAgent",
        task: str,
    ) -> None:
        self._agent = agent
        self._task = task
        self._event_queue: queue.Queue[Optional[tuple[str, dict[str, Any]]]] = (
            queue.Queue(maxsize=100)
        )
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def __iter__(self) -> Iterator[AgentEvent]:
        """返回迭代器."""
        return self  # type: ignore

    def __next__(self) -> AgentEvent:
        """从队列获取下一个事件."""
        try:
            if self._worker_thread is None:
                self._start_worker()

            item = self._event_queue.get(timeout=0.1)

            if item is None:
                raise StopIteration

            event_type, event_data = item
            return AgentEvent(type=event_type, data=event_data)

        except queue.Empty:
            if self._worker_thread and self._worker_thread.is_alive():
                return AgentEvent(
                    type=AgentEventType.STEP.value,
                    data={
                        "step": -1,
                        "thinking": "",
                        "action": None,
                        "success": True,
                        "finished": False,
                    },
                )
            else:
                raise StopIteration

        except StopIteration:
            raise

        except Exception as e:
            self._stop_event.set()
            return AgentEvent(type=AgentEventType.ERROR.value, data={"message": str(e)})

    def _start_worker(self) -> None:
        """启动 worker 线程."""

        def worker():
            try:
                # 检查停止事件
                if self._stop_event.is_set():
                    return

                # 注入 thinking 回调
                # 这是一个 hack，但为了实现 "Zero Agent Change" 目标
                # 假设 agent 有 _thinking_callback 属性
                original_callback = getattr(self._agent, "_thinking_callback", None)

                def on_thinking(chunk: str):
                    self._event_queue.put(
                        (AgentEventType.THINKING.value, {"chunk": chunk})
                    )
                    if original_callback:
                        original_callback(chunk)

                # Monkey-patch thinking callback
                setattr(self._agent, "_thinking_callback", on_thinking)

                try:
                    # 执行 step 循环
                    # 使用会话级别的标记，而不是 agent.step_count
                    # 这样每次新对话开始时，第一步都会传递 task
                    is_first_in_session = True
                    while not self._stop_event.is_set():
                        result = self._agent.step(
                            self._task if is_first_in_session else None
                        )
                        is_first_in_session = False

                        # 发射 step 事件
                        self._event_queue.put(
                            (
                                AgentEventType.STEP.value,
                                {
                                    "step": self._agent.step_count,
                                    "thinking": result.thinking,
                                    "action": result.action,
                                    "success": result.success,
                                    "finished": result.finished,
                                },
                            )
                        )

                        # 检查是否完成
                        if result.finished:
                            # 发射 done 事件
                            self._event_queue.put(
                                (
                                    AgentEventType.DONE.value,
                                    {
                                        "message": result.message,
                                        "steps": self._agent.step_count,
                                        "success": result.success,
                                    },
                                )
                            )
                            break

                        # 检查步数限制
                        if self._agent.step_count >= self._agent.agent_config.max_steps:
                            self._event_queue.put(
                                (
                                    AgentEventType.DONE.value,
                                    {
                                        "message": "Max steps reached",
                                        "steps": self._agent.step_count,
                                        "success": result.success,
                                    },
                                )
                            )
                            break
                finally:
                    # 恢复原始回调
                    setattr(self._agent, "_thinking_callback", original_callback)

            except Exception as e:
                # 发射 error 事件
                self._event_queue.put((AgentEventType.ERROR.value, {"message": str(e)}))

            finally:
                # 标记完成
                self._event_queue.put(None)

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    @contextmanager
    def stream_context(self) -> Iterator[Callable[[], None]]:
        """
        Context manager，自动管理清理.
        """
        self._stop_event.clear()
        try:
            yield self.abort
        finally:
            self._stop_event.set()
            # 等待 worker 完成
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5.0)

            # 清空队列
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except queue.Empty:
                    break

    def abort(self) -> None:
        """中止流式执行."""
        self._stop_event.set()
        if hasattr(self._agent, "abort"):
            self._agent.abort()
