"""scrcpy video streaming implementation."""

import asyncio
import os
import socket
import subprocess
from pathlib import Path


class ScrcpyStreamer:
    """Manages scrcpy server lifecycle and H.264 video streaming."""

    def __init__(
        self,
        device_id: str | None = None,
        max_size: int = 1280,
        bit_rate: int = 2_000_000,
        port: int = 27183,
    ):
        """Initialize ScrcpyStreamer.

        Args:
            device_id: ADB device serial (None for default device)
            max_size: Maximum video dimension
            bit_rate: Video bitrate in bps
            port: TCP port for scrcpy socket
        """
        self.device_id = device_id
        self.max_size = max_size
        self.bit_rate = bit_rate
        self.port = port

        self.scrcpy_process: subprocess.Popen | None = None
        self.tcp_socket: socket.socket | None = None
        self.forward_cleanup_needed = False

        # H.264 parameter sets cache (for new connections to join mid-stream)
        self.cached_sps: bytes | None = None
        self.cached_pps: bytes | None = None
        self.cached_idr: bytes | None = None  # Last IDR frame for immediate playback

        # Find scrcpy-server location
        self.scrcpy_server_path = self._find_scrcpy_server()

    def _find_scrcpy_server(self) -> str:
        """Find scrcpy-server binary path."""
        # Priority 1: Project root directory (for repository version)
        project_root = Path(__file__).parent.parent
        project_server = project_root / "scrcpy-server-v3.3.3"
        if project_server.exists():
            print(f"[ScrcpyStreamer] Using project scrcpy-server: {project_server}")
            return str(project_server)

        # Priority 2: Environment variable
        scrcpy_server = os.getenv("SCRCPY_SERVER_PATH")
        if scrcpy_server and os.path.exists(scrcpy_server):
            print(f"[ScrcpyStreamer] Using env scrcpy-server: {scrcpy_server}")
            return scrcpy_server

        # Priority 3: Common system locations
        paths = [
            "/opt/homebrew/Cellar/scrcpy/3.3.3/share/scrcpy/scrcpy-server",
            "/usr/local/share/scrcpy/scrcpy-server",
            "/usr/share/scrcpy/scrcpy-server",
        ]

        for path in paths:
            if os.path.exists(path):
                print(f"[ScrcpyStreamer] Using system scrcpy-server: {path}")
                return path

        raise FileNotFoundError(
            "scrcpy-server not found. Please put scrcpy-server-v3.3.3 in project root or set SCRCPY_SERVER_PATH."
        )

    async def start(self) -> None:
        """Start scrcpy server and establish connection."""
        try:
            # 0. Kill existing scrcpy server processes on device
            print("[ScrcpyStreamer] Cleaning up existing scrcpy processes...")
            await self._cleanup_existing_server()

            # 1. Push scrcpy-server to device
            print("[ScrcpyStreamer] Pushing server to device...")
            await self._push_server()

            # 2. Setup port forwarding
            print(f"[ScrcpyStreamer] Setting up port forwarding on port {self.port}...")
            await self._setup_port_forward()

            # 3. Start scrcpy server
            print("[ScrcpyStreamer] Starting scrcpy server...")
            await self._start_server()

            # 4. Connect TCP socket
            print("[ScrcpyStreamer] Connecting to TCP socket...")
            await self._connect_socket()
            print("[ScrcpyStreamer] Successfully connected!")

        except Exception as e:
            print(f"[ScrcpyStreamer] Failed to start: {e}")
            import traceback
            traceback.print_exc()
            self.stop()
            raise RuntimeError(f"Failed to start scrcpy server: {e}") from e

    async def _cleanup_existing_server(self) -> None:
        """Kill existing scrcpy server processes on device."""
        cmd_base = ["adb"]
        if self.device_id:
            cmd_base.extend(["-s", self.device_id])

        # Method 1: Try pkill
        cmd = cmd_base + ["shell", "pkill", "-9", "-f", "app_process.*scrcpy"]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()

        # Method 2: Find and kill by PID (more reliable)
        cmd = cmd_base + [
            "shell",
            "ps -ef | grep 'app_process.*scrcpy' | grep -v grep | awk '{print $2}' | xargs kill -9"
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()

        # Method 3: Remove port forward if exists
        cmd_remove_forward = cmd_base + ["forward", "--remove", f"tcp:{self.port}"]
        process = await asyncio.create_subprocess_exec(
            *cmd_remove_forward, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()

        # Wait longer for resources to be released
        print("[ScrcpyStreamer] Waiting for cleanup to complete...")
        await asyncio.sleep(2)

    async def _push_server(self) -> None:
        """Push scrcpy-server to device."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["push", self.scrcpy_server_path, "/data/local/tmp/scrcpy-server"])

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()

    async def _setup_port_forward(self) -> None:
        """Setup ADB port forwarding."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["forward", f"tcp:{self.port}", "localabstract:scrcpy"])

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()
        self.forward_cleanup_needed = True

    async def _start_server(self) -> None:
        """Start scrcpy server on device with retry on address conflict."""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            cmd = ["adb"]
            if self.device_id:
                cmd.extend(["-s", self.device_id])

            # Build server command
            # Note: scrcpy 3.3+ uses different parameter format
            server_args = [
                "shell",
                "CLASSPATH=/data/local/tmp/scrcpy-server",
                "app_process",
                "/",
                "com.genymobile.scrcpy.Server",
                "3.3.3",  # scrcpy version - must match installed version
                f"max_size={self.max_size}",
                f"video_bit_rate={self.bit_rate}",
                "tunnel_forward=true",
                "audio=false",
                "control=false",
                "cleanup=false",
                # Force I-frame (IDR) every 1 second for reliable reconnection
                "video_codec_options=i-frame-interval=1",
            ]
            cmd.extend(server_args)

            # Capture stderr to see error messages
            self.scrcpy_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for server to start
            await asyncio.sleep(2)

            # Check if process is still running
            if self.scrcpy_process.returncode is not None:
                # Process has exited
                stdout, stderr = await self.scrcpy_process.communicate()
                error_msg = stderr.decode() if stderr else stdout.decode()

                # Check if it's an "Address already in use" error
                if "Address already in use" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"[ScrcpyStreamer] Address in use, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                        await self._cleanup_existing_server()
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise RuntimeError(f"scrcpy server failed after {max_retries} attempts: {error_msg}")
                else:
                    raise RuntimeError(f"scrcpy server exited immediately: {error_msg}")

            # Server started successfully
            return

        raise RuntimeError("Failed to start scrcpy server after maximum retries")

    async def _connect_socket(self) -> None:
        """Connect to scrcpy TCP socket."""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.settimeout(5)

        # Retry connection
        for _ in range(5):
            try:
                self.tcp_socket.connect(("localhost", self.port))
                self.tcp_socket.settimeout(None)  # Non-blocking for async
                return
            except (ConnectionRefusedError, OSError):
                await asyncio.sleep(0.5)

        raise ConnectionError("Failed to connect to scrcpy server")

    def _find_nal_units(self, data: bytes) -> list[tuple[int, int, int]]:
        """Find NAL units in H.264 data.

        Returns:
            List of (start_pos, nal_type, nal_size) tuples
        """
        nal_units = []
        i = 0
        data_len = len(data)

        while i < data_len - 4:
            # Look for start codes: 0x00 0x00 0x00 0x01 or 0x00 0x00 0x01
            if data[i:i+4] == b'\x00\x00\x00\x01':
                start_code_len = 4
            elif data[i:i+3] == b'\x00\x00\x01':
                start_code_len = 3
            else:
                i += 1
                continue

            # NAL unit type is in lower 5 bits of first byte after start code
            nal_start = i + start_code_len
            if nal_start >= data_len:
                break

            nal_type = data[nal_start] & 0x1F

            # Find next start code to determine NAL unit size
            next_start = nal_start + 1
            while next_start < data_len - 3:
                if (data[next_start:next_start+4] == b'\x00\x00\x00\x01' or
                    data[next_start:next_start+3] == b'\x00\x00\x01'):
                    break
                next_start += 1
            else:
                next_start = data_len

            nal_size = next_start - i
            nal_units.append((i, nal_type, nal_size))

            i = next_start

        return nal_units

    def _cache_nal_units(self, data: bytes) -> None:
        """Parse and cache important NAL units (SPS, PPS, IDR)."""
        nal_units = self._find_nal_units(data)

        for start, nal_type, size in nal_units:
            nal_data = data[start:start+size]

            if nal_type == 7:  # SPS
                if self.cached_sps != nal_data:
                    self.cached_sps = nal_data
                    print(f"[ScrcpyStreamer] Cached SPS ({size} bytes)")
            elif nal_type == 8:  # PPS
                if self.cached_pps != nal_data:
                    self.cached_pps = nal_data
                    print(f"[ScrcpyStreamer] Cached PPS ({size} bytes)")
            elif nal_type == 5:  # IDR frame
                # Only cache if we have SPS/PPS
                if self.cached_sps and self.cached_pps:
                    self.cached_idr = nal_data
                    # print(f"[ScrcpyStreamer] Cached IDR frame ({size} bytes)")  # Too verbose

    def _prepend_sps_pps_to_idr(self, data: bytes) -> bytes:
        """Prepend SPS/PPS before each IDR frame to ensure decodability.

        This ensures that clients can start decoding from any IDR frame,
        even if they join mid-stream.

        Returns:
            Modified data with SPS/PPS prepended to IDR frames
        """
        if not self.cached_sps or not self.cached_pps:
            return data

        nal_units = self._find_nal_units(data)

        # Find IDR frames and check for existing SPS/PPS
        idr_positions = []
        has_sps = False
        has_pps = False

        for start, nal_type, size in nal_units:
            if nal_type == 7:
                has_sps = True
            elif nal_type == 8:
                has_pps = True
            elif nal_type == 5:  # IDR frame
                idr_positions.append(start)

        # If no IDR or already has SPS/PPS, return original data
        if not idr_positions or (has_sps and has_pps):
            return data

        # Prepend SPS/PPS before first IDR frame
        first_idr_pos = idr_positions[0]
        modified_data = (
            data[:first_idr_pos] +           # Data before IDR
            self.cached_sps +                 # Insert SPS
            self.cached_pps +                 # Insert PPS
            data[first_idr_pos:]             # IDR and rest of data
        )

        print(f"[ScrcpyStreamer] Prepended SPS/PPS before IDR frame")
        return modified_data

    def get_initialization_data(self) -> bytes | None:
        """Get cached SPS/PPS/IDR for initializing new connections.

        Returns:
            Concatenated SPS + PPS + IDR, or None if not available
        """
        if self.cached_sps and self.cached_pps:
            # Return SPS + PPS (+ IDR if available)
            init_data = self.cached_sps + self.cached_pps
            if self.cached_idr:
                init_data += self.cached_idr
            return init_data
        return None

    async def read_h264_chunk(self) -> bytes:
        """Read H.264 data chunk from socket.

        Returns:
            bytes: Raw H.264 data with SPS/PPS prepended to IDR frames

        Raises:
            ConnectionError: If socket is closed or error occurs
        """
        if not self.tcp_socket:
            raise ConnectionError("Socket not connected")

        try:
            # Use asyncio to make socket read non-blocking
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self.tcp_socket.recv, 65536)

            if not data:
                raise ConnectionError("Socket closed by remote")

            # Cache SPS/PPS/IDR for future use
            self._cache_nal_units(data)

            # Automatically prepend SPS/PPS before IDR frames
            # This ensures clients can decode from any IDR frame
            data = self._prepend_sps_pps_to_idr(data)

            return data
        except Exception as e:
            raise ConnectionError(f"Failed to read from socket: {e}") from e

    def stop(self) -> None:
        """Stop scrcpy server and cleanup resources."""
        # Close socket
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None

        # Kill server process
        if self.scrcpy_process:
            try:
                self.scrcpy_process.terminate()
                self.scrcpy_process.wait(timeout=2)
            except Exception:
                try:
                    self.scrcpy_process.kill()
                except Exception:
                    pass
            self.scrcpy_process = None

        # Remove port forwarding
        if self.forward_cleanup_needed:
            try:
                cmd = ["adb"]
                if self.device_id:
                    cmd.extend(["-s", self.device_id])
                cmd.extend(["forward", "--remove", f"tcp:{self.port}"])
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass
            self.forward_cleanup_needed = False

    def __del__(self):
        """Cleanup on destruction."""
        self.stop()
