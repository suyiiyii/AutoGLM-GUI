"""Scrcpy video streaming implementation (ya-webadb protocol aligned)."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from asyncio.subprocess import Process as AsyncProcess

from AutoGLM_GUI.adb_plus import check_device_available
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import is_windows, run_cmd_silently, spawn_process
from AutoGLM_GUI.scrcpy_protocol import (
    PTS_CONFIG,
    PTS_KEYFRAME,
    SCRCPY_CODEC_NAME_TO_ID,
    SCRCPY_KNOWN_CODECS,
    ScrcpyMediaStreamPacket,
    ScrcpyVideoStreamMetadata,
    ScrcpyVideoStreamOptions,
)


async def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Test if TCP port is available for binding.

    Args:
        port: TCP port number
        host: Host address to test

    Returns:
        True if port can be bound (available), False otherwise
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        sock.bind((host, port))
        logger.debug(f"Port {port} is available for binding")
        return True
    except OSError as e:
        # Handle cross-platform errno for "Address already in use"
        # macOS: 48, Linux: 98, Windows: 10048
        logger.debug(f"Port {port} is occupied: {e}")
        return False
    finally:
        if sock:
            sock.close()


async def wait_for_port_release(
    port: int,
    timeout: float = 5.0,
    poll_interval: float = 0.2,
    host: str = "127.0.0.1",
) -> bool:
    """Wait for TCP port to become available with polling.

    Args:
        port: TCP port to wait for
        timeout: Maximum wait time in seconds (default: 5.0)
        poll_interval: Check interval in seconds (default: 0.2)
        host: Host address

    Returns:
        True if port became available, False if timeout
    """
    start_time = time.time()
    attempt = 0

    while time.time() - start_time < timeout:
        attempt += 1
        if await is_port_available(port, host):
            elapsed = time.time() - start_time
            logger.info(
                f"Port {port} became available after {elapsed:.2f}s ({attempt} checks)"
            )
            return True

        # Log progress every second for debugging
        if attempt % 5 == 0:  # Every 1 second (5 * 0.2s)
            elapsed = time.time() - start_time
            logger.debug(f"Still waiting for port {port}... ({elapsed:.1f}s elapsed)")

        await asyncio.sleep(poll_interval)

    logger.warning(f"Port {port} did not release within {timeout}s timeout")
    return False


@dataclass
class ScrcpyServerOptions:
    max_size: int
    bit_rate: int
    max_fps: int
    tunnel_forward: bool
    audio: bool
    control: bool
    cleanup: bool
    video_codec: str
    send_frame_meta: bool
    send_device_meta: bool
    send_codec_meta: bool
    send_dummy_byte: bool
    video_codec_options: str | None


class ScrcpyStreamer:
    """Manages scrcpy server lifecycle and video stream parsing."""

    def __init__(
        self,
        device_id: str | None = None,
        max_size: int = 1280,
        bit_rate: int = 1_000_000,
        port: int = 27183,
        idr_interval_s: int = 1,
        stream_options: ScrcpyVideoStreamOptions | None = None,
    ):
        """Initialize ScrcpyStreamer.

        Args:
            device_id: ADB device serial (None for default device)
            max_size: Maximum video dimension
            bit_rate: Video bitrate in bps
            port: TCP port for scrcpy socket
            idr_interval_s: Seconds between IDR frames (controls GOP length)
            stream_options: Scrcpy protocol options for metadata/frame parsing
        """
        self.device_id = device_id
        self.max_size = max_size
        self.bit_rate = bit_rate
        self.port = port
        self.idr_interval_s = idr_interval_s
        self.stream_options = stream_options or ScrcpyVideoStreamOptions()

        self.scrcpy_process: subprocess.Popen[bytes] | AsyncProcess | None = None
        self.tcp_socket: socket.socket | None = None
        self.forward_cleanup_needed = False

        self._read_buffer = bytearray()
        self._metadata: ScrcpyVideoStreamMetadata | None = None
        self._dummy_byte_skipped = False

        # Find scrcpy-server location
        self.scrcpy_server_path = self._find_scrcpy_server()

    def _find_scrcpy_server(self) -> str:
        """Find scrcpy-server binary path."""
        # Priority 1: PyInstaller bundled path (for packaged executable)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled_server = Path(meipass) / "scrcpy-server-v3.3.3"
            if bundled_server.exists():
                logger.info(f"Using bundled scrcpy-server: {bundled_server}")
                return str(bundled_server)

        # Priority 2: Project root directory (for repository version)
        project_root = Path(__file__).parent.parent
        project_server = project_root / "scrcpy-server-v3.3.3"
        if project_server.exists():
            logger.info(f"Using project scrcpy-server: {project_server}")
            return str(project_server)

        # Priority 3: Environment variable
        scrcpy_server = os.getenv("SCRCPY_SERVER_PATH")
        if scrcpy_server and os.path.exists(scrcpy_server):
            logger.info(f"Using env scrcpy-server: {scrcpy_server}")
            return scrcpy_server

        # Priority 4: Common system locations
        paths = [
            "/opt/homebrew/Cellar/scrcpy/3.3.3/share/scrcpy/scrcpy-server",
            "/usr/local/share/scrcpy/scrcpy-server",
            "/usr/share/scrcpy/scrcpy-server",
        ]

        for path in paths:
            if os.path.exists(path):
                logger.info(f"Using system scrcpy-server: {path}")
                return path

        raise FileNotFoundError(
            "scrcpy-server not found. Please put scrcpy-server-v3.3.3 in project root or set SCRCPY_SERVER_PATH."
        )

    async def start(self) -> None:
        """Start scrcpy server and establish connection."""
        self._read_buffer.clear()
        self._metadata = None
        self._dummy_byte_skipped = False
        logger.debug("Reset stream state")

        try:
            # 0. Check device availability first
            logger.info(f"Checking device {self.device_id} availability...")
            await check_device_available(self.device_id)
            logger.info(f"Device {self.device_id} is available")

            # 1. Kill existing scrcpy server processes on device
            logger.info("Cleaning up existing scrcpy processes...")
            await self._cleanup_existing_server()

            # 2. Push scrcpy-server to device
            logger.info("Pushing server to device...")
            await self._push_server()

            # 3. Setup port forwarding
            logger.info(f"Setting up port forwarding on port {self.port}...")
            await self._setup_port_forward()

            # 4. Start scrcpy server
            logger.info("Starting scrcpy server...")
            await self._start_server()

            # 5. Connect TCP socket
            logger.info("Connecting to TCP socket...")
            await self._connect_socket()
            logger.info("Successfully connected!")

        except Exception as e:
            logger.exception(f"Failed to start: {e}")
            self.stop()
            raise RuntimeError(f"Failed to start scrcpy server: {e}") from e

    async def _cleanup_existing_server(self) -> None:
        """Kill existing scrcpy server processes and wait for port release."""
        cmd_base = ["adb"]
        if self.device_id:
            cmd_base.extend(["-s", self.device_id])

        # Method 1: Try pkill
        logger.debug("Killing scrcpy processes via pkill...")
        cmd = cmd_base + ["shell", "pkill", "-9", "-f", "app_process.*scrcpy"]
        await run_cmd_silently(cmd)

        # Method 2: Find and kill by PID (more reliable)
        logger.debug("Killing scrcpy processes via PID...")
        cmd = cmd_base + [
            "shell",
            "ps -ef | grep 'app_process.*scrcpy' | grep -v grep | awk '{print $2}' | xargs kill -9",
        ]
        await run_cmd_silently(cmd)

        # Method 3: Remove port forward
        logger.debug(f"Removing ADB port forward on port {self.port}...")
        cmd_remove_forward = cmd_base + ["forward", "--remove", f"tcp:{self.port}"]
        await run_cmd_silently(cmd_remove_forward)

        # Wait for port to be truly available (instead of fixed sleep)
        logger.info(f"Waiting for port {self.port} to be released...")
        port_released = await wait_for_port_release(
            self.port,
            timeout=5.0,  # Max 5 seconds (vs old fixed 2s)
            poll_interval=0.2,  # Check every 200ms
        )

        if not port_released:
            logger.warning(
                f"Port {self.port} still occupied after cleanup. "
                "Will attempt to start anyway (may fail)."
            )
        else:
            logger.info(f"Port {self.port} successfully released and ready")

    async def _push_server(self) -> None:
        """Push scrcpy-server to device."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["push", self.scrcpy_server_path, "/data/local/tmp/scrcpy-server"])

        await run_cmd_silently(cmd)

    async def _setup_port_forward(self) -> None:
        """Setup ADB port forwarding."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["forward", f"tcp:{self.port}", "localabstract:scrcpy"])

        await run_cmd_silently(cmd)
        self.forward_cleanup_needed = True

    def _build_server_options(self) -> ScrcpyServerOptions:
        codec_options = f"i-frame-interval={self.idr_interval_s}"
        return ScrcpyServerOptions(
            max_size=self.max_size,
            bit_rate=self.bit_rate,
            max_fps=20,
            tunnel_forward=True,
            audio=False,
            control=False,
            cleanup=False,
            video_codec=self.stream_options.video_codec,
            send_frame_meta=self.stream_options.send_frame_meta,
            send_device_meta=self.stream_options.send_device_meta,
            send_codec_meta=self.stream_options.send_codec_meta,
            send_dummy_byte=self.stream_options.send_dummy_byte,
            video_codec_options=codec_options,
        )

    async def _start_server(self) -> None:
        """Start scrcpy server on device with intelligent retry."""
        max_retries = 3
        retry_delay = 1.0  # Reduced from 2s (cleanup handles waiting now)

        options = self._build_server_options()

        for attempt in range(max_retries):
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])

            # Build server command
            server_args = [
                "shell",
                "CLASSPATH=/data/local/tmp/scrcpy-server",
                "app_process",
                "/",
                "com.genymobile.scrcpy.Server",
                "3.3.3",
                f"max_size={options.max_size}",
                f"video_bit_rate={options.bit_rate}",
                f"max_fps={options.max_fps}",
                f"tunnel_forward={str(options.tunnel_forward).lower()}",
                f"audio={str(options.audio).lower()}",
                f"control={str(options.control).lower()}",
                f"cleanup={str(options.cleanup).lower()}",
                f"video_codec={options.video_codec}",
                f"send_frame_meta={str(options.send_frame_meta).lower()}",
                f"send_device_meta={str(options.send_device_meta).lower()}",
                f"send_codec_meta={str(options.send_codec_meta).lower()}",
                f"send_dummy_byte={str(options.send_dummy_byte).lower()}",
                f"video_codec_options={options.video_codec_options}",
            ]
            cmd.extend(server_args)

            self.scrcpy_process = await spawn_process(cmd, capture_output=True)

            # Wait for server to start
            await asyncio.sleep(2)

            # Check if process is still running
            error_msg = None
            proc = self.scrcpy_process
            if proc is not None:
                if is_windows():
                    if proc.poll() is not None:  # type: ignore[union-attr]
                        stdout, stderr = proc.communicate()  # type: ignore[union-attr]
                        error_msg = stderr.decode() if stderr else stdout.decode()
                else:
                    if proc.returncode is not None:  # type: ignore[union-attr]
                        stdout, stderr = await proc.communicate()  # type: ignore[union-attr]
                        error_msg = stderr.decode() if stderr else stdout.decode()

            if error_msg is not None:
                # Detailed error classification
                if "Address already in use" in error_msg:
                    logger.error(
                        f"Port {self.port} conflict detected (attempt {attempt + 1}/{max_retries}). "
                        f"Error: {error_msg[:200]}"
                    )
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Retrying with aggressive cleanup in {retry_delay}s..."
                        )
                        await self._cleanup_existing_server()
                        await asyncio.sleep(retry_delay)
                        continue
                    # Specific error for port conflicts
                    raise RuntimeError(
                        f"Port {self.port} persistently occupied after {max_retries} attempts. "
                        "Please check if another scrcpy instance is running."
                    )
                else:
                    # Non-port errors fail immediately (no retry)
                    logger.error(f"Scrcpy server startup failed: {error_msg[:200]}")
                    raise RuntimeError(f"Scrcpy server failed to start: {error_msg}")

            logger.info("Scrcpy server started successfully")
            return

        raise RuntimeError("Failed to start scrcpy server after maximum retries")

    async def _connect_socket(self) -> None:
        """Connect to scrcpy TCP socket."""
        # Retry connection with exponential backoff (max ~6 seconds total)
        max_attempts = 10
        retry_delay = 0.3

        for attempt in range(max_attempts):
            # Create a fresh socket for each attempt to avoid "Invalid argument" error
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
            except OSError as e:
                logger.debug(f"Failed to set socket buffer size: {e}")

            try:
                sock.connect(("localhost", self.port))
                sock.settimeout(None)
                self.tcp_socket = sock  # Only assign on success
                logger.debug(f"Connected to scrcpy server on attempt {attempt + 1}")
                return
            except (ConnectionRefusedError, OSError) as e:
                # Close the failed socket
                try:
                    sock.close()
                except Exception:
                    pass

                if attempt < max_attempts - 1:
                    logger.debug(
                        f"Connection attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    # Gradually increase delay for later attempts
                    if attempt >= 3:
                        retry_delay = 0.5
                else:
                    logger.error(
                        f"Failed to connect after {max_attempts} attempts. "
                        f"Last error: {e}"
                    )

        raise ConnectionError("Failed to connect to scrcpy server")

    async def _read_exactly(self, size: int) -> bytes:
        if not self.tcp_socket:
            raise ConnectionError("Socket not connected")

        while len(self._read_buffer) < size:
            chunk = await asyncio.to_thread(
                self.tcp_socket.recv, max(4096, size - len(self._read_buffer))
            )
            if not chunk:
                raise ConnectionError("Socket closed by remote")
            self._read_buffer.extend(chunk)

        data = bytes(self._read_buffer[:size])
        del self._read_buffer[:size]
        return data

    async def _read_u16(self) -> int:
        return int.from_bytes(await self._read_exactly(2), "big")

    async def _read_u32(self) -> int:
        return int.from_bytes(await self._read_exactly(4), "big")

    async def _read_u64(self) -> int:
        return int.from_bytes(await self._read_exactly(8), "big")

    async def read_video_metadata(self) -> ScrcpyVideoStreamMetadata:
        """Read and cache video stream metadata from scrcpy."""
        if self._metadata is not None:
            return self._metadata

        if self.stream_options.send_dummy_byte and not self._dummy_byte_skipped:
            await self._read_exactly(1)
            self._dummy_byte_skipped = True

        device_name = None
        width = None
        height = None
        codec = SCRCPY_CODEC_NAME_TO_ID.get(
            self.stream_options.video_codec, SCRCPY_CODEC_NAME_TO_ID["h264"]
        )

        if self.stream_options.send_device_meta:
            raw_name = await self._read_exactly(64)
            device_name = raw_name.split(b"\x00", 1)[0].decode(
                "utf-8", errors="replace"
            )

        if self.stream_options.send_codec_meta:
            codec_value = await self._read_u32()
            if codec_value in SCRCPY_KNOWN_CODECS:
                codec = codec_value
                width = await self._read_u32()
                height = await self._read_u32()
            else:
                # Legacy fallback: treat codec_value as width/height u16
                width = (codec_value >> 16) & 0xFFFF
                height = codec_value & 0xFFFF
        else:
            if self.stream_options.send_device_meta:
                width = await self._read_u16()
                height = await self._read_u16()

        self._metadata = ScrcpyVideoStreamMetadata(
            device_name=device_name,
            width=width,
            height=height,
            codec=codec,
        )
        return self._metadata

    async def read_media_packet(self) -> ScrcpyMediaStreamPacket:
        """Read one Scrcpy media packet (configuration/data)."""
        if not self.stream_options.send_frame_meta:
            raise RuntimeError(
                "send_frame_meta is disabled; packet parsing unavailable"
            )

        if self._metadata is None:
            await self.read_video_metadata()

        pts = await self._read_u64()
        data_length = await self._read_u32()
        payload = await self._read_exactly(data_length)

        if pts == PTS_CONFIG:
            return ScrcpyMediaStreamPacket(type="configuration", data=payload)

        if pts & PTS_KEYFRAME:
            return ScrcpyMediaStreamPacket(
                type="data",
                data=payload,
                keyframe=True,
                pts=pts & ~PTS_KEYFRAME,
            )

        return ScrcpyMediaStreamPacket(
            type="data",
            data=payload,
            keyframe=False,
            pts=pts,
        )

    async def iter_packets(self):
        """Yield packets continuously from the scrcpy stream."""
        while True:
            yield await self.read_media_packet()

    def stop(self) -> None:
        """Stop scrcpy server and cleanup resources."""
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None

        if self.scrcpy_process:
            try:
                self.scrcpy_process.terminate()
                if isinstance(self.scrcpy_process, subprocess.Popen):
                    self.scrcpy_process.wait(timeout=2)
            except Exception:
                try:
                    self.scrcpy_process.kill()
                except Exception:
                    pass
            self.scrcpy_process = None

        if self.forward_cleanup_needed:
            try:
                cmd = ["adb"]
                if self.device_id:
                    cmd.extend(["-s", self.device_id])
                cmd.extend(["forward", "--remove", f"tcp:{self.port}"])
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
            except Exception:
                pass
            self.forward_cleanup_needed = False

    def __del__(self):
        self.stop()
