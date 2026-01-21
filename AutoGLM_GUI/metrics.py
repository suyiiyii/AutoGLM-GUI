"""Prometheus metrics collector for AutoGLM-GUI."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from prometheus_client.core import CollectorRegistry, GaugeMetricFamily
from prometheus_client.registry import Collector

if TYPE_CHECKING:
    from prometheus_client.core import Metric

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.version import APP_VERSION


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
            with device_manager._devices_lock:
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
        with manager._streaming_contexts_lock:
            streaming_count = len(manager._streaming_contexts)

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

        with manager._devices_lock:
            devices_snapshot = list(manager._devices.values())

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
