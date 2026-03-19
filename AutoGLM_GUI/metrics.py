"""Prometheus metrics collector for AutoGLM-GUI."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from prometheus_client.core import (
    CollectorRegistry,
    GaugeMetricFamily,
    HistogramMetricFamily,
)
from prometheus_client.registry import Collector

if TYPE_CHECKING:
    from prometheus_client.core import Metric

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.version import APP_VERSION


_TASK_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
_STEP_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
_COMPONENT_DURATION_BUCKETS = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
)
_TRACE_COMPONENT_FIELDS = {
    "screenshot": "screenshot_duration_ms",
    "current_app": "current_app_duration_ms",
    "llm": "llm_duration_ms",
    "parse_action": "parse_action_duration_ms",
    "execute_action": "execute_action_duration_ms",
    "update_context": "update_context_duration_ms",
    "adb": "adb_duration_ms",
    "sleep": "sleep_duration_ms",
    "other": "other_duration_ms",
}


@dataclass
class _HistogramAggregate:
    bucket_bounds: tuple[float, ...]
    bucket_counts: list[int] = field(init=False)
    count: int = 0
    sum_value: float = 0.0

    def __post_init__(self) -> None:
        self.bucket_counts = [0 for _ in self.bucket_bounds]

    def observe(self, value: float) -> None:
        safe_value = max(value, 0.0)
        self.count += 1
        self.sum_value += safe_value

        for index, upper_bound in enumerate(self.bucket_bounds):
            if safe_value <= upper_bound:
                self.bucket_counts[index] += 1
                return

    def to_prometheus_buckets(self) -> list[tuple[str, float]]:
        cumulative = 0.0
        buckets: list[tuple[str, float]] = []
        for upper_bound, bucket_count in zip(self.bucket_bounds, self.bucket_counts):
            cumulative += bucket_count
            buckets.append((str(upper_bound), cumulative))

        buckets.append(("+Inf", float(self.count)))
        return buckets


class _TraceLatencyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._task_histograms: dict[tuple[str], _HistogramAggregate] = {}
        self._step_histograms: dict[tuple[str], _HistogramAggregate] = {}
        self._component_histograms: dict[tuple[str, str], _HistogramAggregate] = {}

    def record_trace_metrics(
        self,
        *,
        source: str,
        trace_summary: dict[str, object] | None,
        step_summaries: list[dict[str, object]],
    ) -> None:
        with self._lock:
            if trace_summary is not None:
                total_duration_seconds = (
                    _coerce_to_float(trace_summary.get("total_duration_ms")) / 1000.0
                )
                if total_duration_seconds > 0:
                    self._get_task_histogram((source,)).observe(total_duration_seconds)

            for step_summary in step_summaries:
                step_duration_seconds = (
                    _coerce_to_float(step_summary.get("total_duration_ms")) / 1000.0
                )
                if step_duration_seconds > 0:
                    self._get_step_histogram((source,)).observe(step_duration_seconds)

                for component, field_name in _TRACE_COMPONENT_FIELDS.items():
                    component_duration_seconds = (
                        _coerce_to_float(step_summary.get(field_name)) / 1000.0
                    )
                    if component_duration_seconds <= 0:
                        continue
                    self._get_component_histogram((source, component)).observe(
                        component_duration_seconds
                    )

    def reset(self) -> None:
        with self._lock:
            self._task_histograms.clear()
            self._step_histograms.clear()
            self._component_histograms.clear()

    def snapshot(
        self,
    ) -> tuple[
        dict[tuple[str], _HistogramAggregate],
        dict[tuple[str], _HistogramAggregate],
        dict[tuple[str, str], _HistogramAggregate],
    ]:
        with self._lock:
            return (
                dict(self._task_histograms),
                dict(self._step_histograms),
                dict(self._component_histograms),
            )

    def _get_task_histogram(self, key: tuple[str]) -> _HistogramAggregate:
        histogram = self._task_histograms.get(key)
        if histogram is None:
            histogram = _HistogramAggregate(_TASK_DURATION_BUCKETS)
            self._task_histograms[key] = histogram
        return histogram

    def _get_step_histogram(self, key: tuple[str]) -> _HistogramAggregate:
        histogram = self._step_histograms.get(key)
        if histogram is None:
            histogram = _HistogramAggregate(_STEP_DURATION_BUCKETS)
            self._step_histograms[key] = histogram
        return histogram

    def _get_component_histogram(self, key: tuple[str, str]) -> _HistogramAggregate:
        histogram = self._component_histograms.get(key)
        if histogram is None:
            histogram = _HistogramAggregate(_COMPONENT_DURATION_BUCKETS)
            self._component_histograms[key] = histogram
        return histogram


_trace_latency_store = _TraceLatencyStore()


def _coerce_to_float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


class AutoGLMMetricsCollector(Collector):
    """
    Custom Prometheus collector for AutoGLM-GUI metrics.

    Implements on-demand metric collection to avoid:
    - Stale metric data
    - Memory leaks from unbounded label cardinality
    - Complexity of background metric updates

    Thread Safety:
    - Acquires manager locks during collect() only
    - Read-only operations (no state modification)
    - Uses shallow copies where needed
    """

    def collect(self) -> list[Metric]:
        """
        Called by Prometheus client on each scrape.

        Returns:
            List of MetricFamily objects
        """
        metrics = []

        try:
            # Agent metrics
            metrics.extend(self._collect_agent_metrics())

            # Device metrics
            metrics.extend(self._collect_device_metrics())

            # Trace latency metrics
            metrics.extend(self._collect_trace_latency_metrics())

            # Build info
            metrics.append(self._collect_build_info())

        except Exception as e:
            logger.error(f"Error collecting Prometheus metrics: {e}")

        return metrics

    def _collect_agent_metrics(self) -> list[Metric]:
        """Collect agent-related metrics (high priority only)."""
        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.phone_agent_manager import AgentState, PhoneAgentManager

        metrics = []
        manager = PhoneAgentManager.get_instance()
        device_manager = DeviceManager.get_instance()

        # Metric 1: autoglm_agents_total (per-agent state)
        agents_gauge = GaugeMetricFamily(
            "autoglm_agents_total",
            "Agent state by device",
            labels=["device_id", "serial", "state"],
        )

        # Metric 4: autoglm_agent_last_used_timestamp_seconds
        last_used_gauge = GaugeMetricFamily(
            "autoglm_agent_last_used_timestamp_seconds",
            "Agent last used timestamp",
            labels=["device_id", "serial"],
        )

        # Metric 5: autoglm_agent_created_timestamp_seconds
        created_gauge = GaugeMetricFamily(
            "autoglm_agent_created_timestamp_seconds",
            "Agent creation timestamp",
            labels=["device_id", "serial"],
        )

        busy_count = 0

        with manager._manager_lock:
            # Get snapshot (shallow copy to minimize lock time)
            metadata_snapshot = dict(manager._metadata)

        # Iterate over _metadata (state is stored in AgentMetadata.state)
        for device_id, metadata in metadata_snapshot.items():
            state = metadata.state

            # Get serial from DeviceManager
            device = device_manager.get_device_by_device_id(device_id)
            serial = device.serial if device else "unknown"

            # Per-agent state (1 for actual state, 0 for others)
            for agent_state in AgentState:
                value = 1 if state == agent_state else 0
                agents_gauge.add_metric(
                    [device_id, serial, agent_state.value],
                    value,
                )

            # Count busy agents
            if state == AgentState.BUSY:
                busy_count += 1

            # Timestamps from metadata
            last_used_gauge.add_metric(
                [device_id, serial],
                metadata.last_used,
            )
            created_gauge.add_metric(
                [device_id, serial],
                metadata.created_at,
            )

        metrics.extend([agents_gauge, last_used_gauge, created_gauge])

        # Metric 2: autoglm_agents_busy_count
        busy_gauge = GaugeMetricFamily(
            "autoglm_agents_busy_count",
            "Number of busy agents",
        )
        busy_gauge.add_metric([], busy_count)
        metrics.append(busy_gauge)

        # Metric 3: autoglm_streaming_sessions_active
        with manager._manager_lock:
            streaming_count = sum(
                1 for m in manager._metadata.values() if m.abort_handler is not None
            )

        streaming_gauge = GaugeMetricFamily(
            "autoglm_streaming_sessions_active",
            "Active streaming agent sessions",
        )
        streaming_gauge.add_metric([], streaming_count)
        metrics.append(streaming_gauge)

        return metrics

    def _collect_device_metrics(self) -> list[Metric]:
        """Collect device-related metrics (high priority only)."""
        from AutoGLM_GUI.device_manager import DeviceManager, DeviceState

        metrics = []
        manager = DeviceManager.get_instance()

        # Metric 6: autoglm_devices_total
        devices_gauge = GaugeMetricFamily(
            "autoglm_devices_total",
            "Device state by serial",
            labels=["serial", "model", "state", "connection_type", "status"],
        )

        # Metric 8: autoglm_device_connections_total
        connections_gauge = GaugeMetricFamily(
            "autoglm_device_connections_total",
            "Connection count by type",
            labels=["serial", "connection_type", "status"],
        )

        # Metric 10: autoglm_device_last_seen_timestamp_seconds
        last_seen_gauge = GaugeMetricFamily(
            "autoglm_device_last_seen_timestamp_seconds",
            "Device last seen timestamp",
            labels=["serial", "model"],
        )

        online_count = 0
        unauthorized_count = 0

        devices_snapshot = manager.get_connected_devices()

        # Process connected devices
        for device in devices_snapshot:
            model = device.model or "unknown"

            # Per-device state
            for dev_state in DeviceState:
                value = 1 if device.state == dev_state else 0
                devices_gauge.add_metric(
                    [
                        device.serial,
                        model,
                        dev_state.value,
                        device.connection_type.value,
                        device.status,
                    ],
                    value,
                )

            # Count online devices
            if device.state == DeviceState.ONLINE:
                online_count += 1

            # Connection breakdown
            for conn in device.connections:
                connections_gauge.add_metric(
                    [device.serial, conn.connection_type.value, conn.status],
                    1,  # Each connection counts as 1
                )

                if conn.status == "unauthorized":
                    unauthorized_count += 1

            # Last seen timestamp
            last_seen_gauge.add_metric([device.serial, model], device.last_seen)

        metrics.extend(
            [
                devices_gauge,
                connections_gauge,
                last_seen_gauge,
            ]
        )

        # Metric 7: autoglm_devices_online_count
        online_gauge = GaugeMetricFamily(
            "autoglm_devices_online_count",
            "Number of online devices",
        )
        online_gauge.add_metric([], online_count)
        metrics.append(online_gauge)

        # Metric 9: autoglm_device_unauthorized_connections_total
        unauth_gauge = GaugeMetricFamily(
            "autoglm_device_unauthorized_connections_total",
            "Total unauthorized connections",
        )
        unauth_gauge.add_metric([], unauthorized_count)
        metrics.append(unauth_gauge)

        return metrics

    def _collect_build_info(self) -> Metric:
        """Collect build information."""
        build_info = GaugeMetricFamily(
            "autoglm_build_info",
            "Build information",
            labels=["version", "python_version"],
        )

        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        build_info.add_metric([APP_VERSION, python_version], 1)

        return build_info

    def _collect_trace_latency_metrics(self) -> list[Metric]:
        """Collect aggregated trace latency metrics."""
        metrics = []
        task_snapshot, step_snapshot, component_snapshot = (
            _trace_latency_store.snapshot()
        )

        task_histogram = HistogramMetricFamily(
            "autoglm_trace_task_duration_seconds",
            "Task execution duration aggregated from trace summaries",
            labels=["source"],
        )
        for labels, histogram in task_snapshot.items():
            task_histogram.add_metric(
                labels,
                histogram.to_prometheus_buckets(),
                histogram.sum_value,
            )
        metrics.append(task_histogram)

        step_histogram = HistogramMetricFamily(
            "autoglm_trace_step_duration_seconds",
            "Per-step execution duration aggregated from trace summaries",
            labels=["source"],
        )
        for labels, histogram in step_snapshot.items():
            step_histogram.add_metric(
                labels,
                histogram.to_prometheus_buckets(),
                histogram.sum_value,
            )
        metrics.append(step_histogram)

        component_histogram = HistogramMetricFamily(
            "autoglm_trace_component_duration_seconds",
            "Trace component duration aggregated from per-step summaries",
            labels=["source", "component"],
        )
        for labels, histogram in component_snapshot.items():
            component_histogram.add_metric(
                labels,
                histogram.to_prometheus_buckets(),
                histogram.sum_value,
            )
        metrics.append(component_histogram)

        return metrics


# Global collector instance (registered once)
_collector_registry: CollectorRegistry | None = None
_collector_instance: AutoGLMMetricsCollector | None = None


def get_metrics_registry() -> CollectorRegistry:
    """
    Get or create the Prometheus registry with AutoGLM collector.

    Returns:
        CollectorRegistry: Registry instance for prometheus_client
    """
    global _collector_registry, _collector_instance

    if _collector_registry is None:
        _collector_registry = CollectorRegistry()
        _collector_instance = AutoGLMMetricsCollector()
        _collector_registry.register(_collector_instance)
        logger.info("Prometheus metrics collector registered")

    return _collector_registry


def record_trace_latency_metrics(
    *,
    source: str,
    trace_summary: dict[str, object] | None,
    step_summaries: list[dict[str, object]],
) -> None:
    """Record aggregated trace timings for Prometheus export."""
    _trace_latency_store.record_trace_metrics(
        source=source,
        trace_summary=trace_summary,
        step_summaries=step_summaries,
    )


def reset_trace_latency_metrics() -> None:
    """Reset in-memory trace latency metrics. Used by tests."""
    _trace_latency_store.reset()
