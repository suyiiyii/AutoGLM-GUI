"""QR code-based wireless ADB pairing module.

This module provides QR code pairing functionality for Android 11+ devices
with wireless debugging support. It generates QR codes and listens for mDNS
service advertisements to automatically pair and connect devices.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, Tuple

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import run_cmd_silently_sync

# mDNS service types
PAIR_SERVICE_TYPE = "_adb-tls-pairing._tcp.local."
CONNECT_SERVICE_TYPE = "_adb-tls-connect._tcp.local."

# QR code payload format
QR_PAYLOAD_TEMPLATE = "WIFI:T:ADB;S:{name};P:{password};;"

# Success indicators in ADB output
SUCCESS_PAIR = "Successfully paired"
SUCCESS_CONNECT = "connected"


@dataclass
class PairingSession:
    """Represents an active QR pairing session."""

    session_id: str
    name: str  # Session name (S field in QR code)
    password: str  # Pairing password (P field in QR code)
    qr_payload: str  # Full QR code payload
    status: str  # Current status: "listening" | "pairing" | "paired" | "connecting" | "connected" | "timeout" | "error"
    device_id: Optional[str] = None  # Device ID after connection (ip:port)
    error_message: Optional[str] = None  # Error details if status is "error"
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    expires_at: float = 0.0  # Unix timestamp when session expires
    zeroconf: Optional[Zeroconf] = None  # Zeroconf instance
    listener: Optional[QRPairingListener] = None  # Service listener
    thread: Optional[threading.Thread] = None  # Listener thread


def _pick_host_from_info(info) -> Optional[str]:
    """Extract preferred host from service info (IPv4 preferred)."""
    try:
        # Prefer IPv4 addresses
        addrs = info.parsed_addresses()
        for addr in addrs:
            # Simple IPv4 pattern check
            parts = addr.split(".")
            if len(parts) == 4 and all(
                p.isdigit() and 0 <= int(p) <= 255 for p in parts
            ):
                return addr
        # Fallback to first address
        if addrs:
            return addrs[0]
    except Exception:
        pass

    # Fallback to mDNS hostname (.local.)
    if hasattr(info, "server") and info.server:
        return info.server.rstrip(".")

    return None


def _adb_pair(host: str, port: int, password: str, adb_path: str = "adb") -> bool:
    """Execute ADB pair command."""
    logger.info(f"[QR Pair] Executing: adb pair {host}:{port}")
    result = run_cmd_silently_sync(
        [adb_path, "pair", f"{host}:{port}", password], timeout=25
    )
    output = result.stdout.strip()
    logger.debug(f"[QR Pair] Pair output: {output}")

    success = result.returncode == 0 and SUCCESS_PAIR in output
    if success:
        logger.info(f"[QR Pair] Successfully paired with {host}:{port}")
    else:
        logger.warning(f"[QR Pair] Pairing failed for {host}:{port}: {output}")

    return success


def _adb_connect(host: str, port: int, adb_path: str = "adb") -> bool:
    """Execute ADB connect command."""
    logger.info(f"[QR Pair] Executing: adb connect {host}:{port}")
    result = run_cmd_silently_sync([adb_path, "connect", f"{host}:{port}"], timeout=20)
    output = result.stdout.strip()
    logger.debug(f"[QR Pair] Connect output: {output}")

    success = result.returncode == 0 and SUCCESS_CONNECT in output.lower()
    if success:
        logger.info(f"[QR Pair] Successfully connected to {host}:{port}")
    else:
        logger.warning(f"[QR Pair] Connection failed for {host}:{port}: {output}")

    return success


class QRPairingListener(ServiceListener):
    """mDNS service listener for QR pairing."""

    def __init__(self, session: PairingSession, adb_path: str):
        self.session = session
        self.adb_path = adb_path

        self.paired: bool = False
        self.connected: bool = False

        self.attempted_pair: Set[Tuple[str, int]] = set()
        self.attempted_connect: Set[Tuple[str, int]] = set()

        self.last_paired_host: Optional[str] = None

    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        """Handle new service discovery."""
        info = zc.get_service_info(service_type, name, timeout=3000)
        if not info:
            logger.debug(f"[QR Pair] No info for service: {name}")
            return

        host = _pick_host_from_info(info)
        if not host:
            logger.debug(f"[QR Pair] No valid host for service: {name}")
            return

        port = info.port
        if port is None:
            logger.debug(f"[QR Pair] No valid port for service: {name}")
            return

        key = (host, port)

        # Handle pairing service
        if service_type == PAIR_SERVICE_TYPE and not self.paired:
            if key in self.attempted_pair:
                logger.debug(f"[QR Pair] Already attempted pairing for {host}:{port}")
                return
            self.attempted_pair.add(key)

            logger.info(f"[QR Pair] Found pairing service: {name} -> {host}:{port}")
            self.session.status = "pairing"

            success = _adb_pair(host, port, self.session.password, self.adb_path)
            if success:
                self.paired = True
                self.last_paired_host = host
                self.session.status = "paired"
                logger.info("[QR Pair] Pairing OK. Waiting for connect service...")

        # Handle connect service
        if service_type == CONNECT_SERVICE_TYPE and self.paired and not self.connected:
            # Prefer same host as paired if we have it
            if self.last_paired_host and host != self.last_paired_host:
                logger.debug(
                    f"[QR Pair] Skipping connect service on different host: {host} (expected {self.last_paired_host})"
                )
                return

            if key in self.attempted_connect:
                logger.debug(
                    f"[QR Pair] Already attempted connection for {host}:{port}"
                )
                return
            self.attempted_connect.add(key)

            logger.info(f"[QR Pair] Found connect service: {name} -> {host}:{port}")
            self.session.status = "connecting"

            success = _adb_connect(host, port, self.adb_path)
            if success:
                self.connected = True
                self.session.status = "connected"
                self.session.device_id = f"{host}:{port}"
                logger.info(f"[QR Pair] Connected! Device ID: {self.session.device_id}")

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        """Handle service updates (treat as adds)."""
        self.add_service(zc, service_type, name)

    def remove_service(self, _zc: Zeroconf, _service_type: str, _name: str) -> None:
        """Handle service removal (no action needed)."""
        pass


class QRPairingManager:
    """Manages active QR pairing sessions."""

    def __init__(self):
        self._sessions: Dict[str, PairingSession] = {}

    def create_session(
        self, timeout: int = 90, adb_path: str = "adb"
    ) -> PairingSession:
        """Create a new pairing session with QR code.

        Args:
            timeout: Session timeout in seconds (default 90)
            adb_path: Path to ADB executable (default "adb")

        Returns:
            PairingSession with generated QR code payload
        """
        session_id = str(uuid.uuid4())
        name = f"debug-{secrets.token_hex(4)}"  # 8 hex chars
        password = secrets.token_hex(8)  # 16 hex chars (64-bit entropy)
        qr_payload = QR_PAYLOAD_TEMPLATE.format(name=name, password=password)

        now = datetime.now().timestamp()
        session = PairingSession(
            session_id=session_id,
            name=name,
            password=password,
            qr_payload=qr_payload,
            status="listening",
            created_at=now,
            expires_at=now + timeout,
        )

        # Start mDNS listener in background thread
        self._start_listener(session, adb_path)

        self._sessions[session_id] = session
        logger.info(f"[QR Pair] Created session {session_id} (timeout={timeout}s)")
        logger.debug(f"[QR Pair] QR payload: {qr_payload}")

        return session

    def _start_listener(self, session: PairingSession, adb_path: str):
        """Start zeroconf listener (runs in thread pool to avoid blocking)."""

        def _listen():
            """Listener thread function."""
            try:
                zc = Zeroconf()
                listener = QRPairingListener(session, adb_path)
                session.zeroconf = zc
                session.listener = listener

                # Register service browsers
                ServiceBrowser(zc, PAIR_SERVICE_TYPE, listener)
                ServiceBrowser(zc, CONNECT_SERVICE_TYPE, listener)

                logger.info(
                    f"[QR Pair] Listening for mDNS services ({PAIR_SERVICE_TYPE}, {CONNECT_SERVICE_TYPE})"
                )

                # Wait until timeout or connected
                deadline = session.expires_at
                while datetime.now().timestamp() < deadline:
                    if listener.connected:
                        logger.info("[QR Pair] Listener detected connection, stopping")
                        break
                    # Sleep in small increments to check frequently
                    import time

                    time.sleep(0.2)

                # Check final status
                if not listener.connected:
                    session.status = "timeout"
                    logger.warning(f"[QR Pair] Session {session.session_id} timed out")

            except Exception as e:
                logger.exception(f"[QR Pair] Listener error: {e}")
                session.status = "error"
                session.error_message = str(e)
            finally:
                # Cleanup zeroconf
                if session.zeroconf:
                    try:
                        session.zeroconf.close()
                        logger.debug(
                            f"[QR Pair] Zeroconf closed for session {session.session_id}"
                        )
                    except Exception as e:
                        logger.error(f"[QR Pair] Error closing zeroconf: {e}")

        # Run in dedicated thread (non-blocking for FastAPI)
        thread = threading.Thread(
            target=_listen,
            name=f"QRPairing-{session.session_id[:8]}",
            daemon=True,  # 守护线程,主程序退出时自动终止
        )
        session.thread = thread
        thread.start()
        logger.debug(
            f"[QR Pair] Started listener thread for session {session.session_id}"
        )

    def get_session(self, session_id: str) -> Optional[PairingSession]:
        """Get session by ID.

        Args:
            session_id: Session UUID

        Returns:
            PairingSession if found, None otherwise
        """
        return self._sessions.get(session_id)

    def cancel_session(self, session_id: str) -> bool:
        """Cancel and cleanup a session.

        Args:
            session_id: Session UUID to cancel

        Returns:
            True if session was found and cancelled, False otherwise
        """
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"[QR Pair] Cancelling session {session_id}")

            # Close zeroconf (this will cause the listener thread to exit)
            if session.zeroconf:
                try:
                    session.zeroconf.close()
                    logger.debug(
                        f"[QR Pair] Zeroconf closed for cancelled session {session_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"[QR Pair] Error closing zeroconf during cancellation: {e}"
                    )

            # Wait for thread to finish (with timeout)
            if session.thread and session.thread.is_alive():
                logger.debug("[QR Pair] Waiting for listener thread to finish...")
                session.thread.join(timeout=2.0)  # 最多等待2秒
                if session.thread.is_alive():
                    logger.warning(
                        "[QR Pair] Listener thread did not finish in time (will be abandoned as daemon)"
                    )

            return True
        else:
            logger.warning(f"[QR Pair] Session {session_id} not found for cancellation")
            return False

    async def cleanup_expired_sessions(self):
        """Background task to cleanup expired sessions.

        Runs indefinitely, checking every 60 seconds for expired sessions.
        """
        logger.info("[QR Pair] Starting cleanup task")
        while True:
            await asyncio.sleep(60)  # Check every minute
            now = datetime.now().timestamp()
            expired = [
                sid for sid, sess in self._sessions.items() if now > sess.expires_at
            ]

            for sid in expired:
                logger.info(f"[QR Pair] Cleaning up expired session {sid}")
                self.cancel_session(sid)


# Global singleton instance
qr_pairing_manager = QRPairingManager()
