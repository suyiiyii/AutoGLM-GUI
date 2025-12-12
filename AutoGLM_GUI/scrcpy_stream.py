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
        bit_rate: int = 1_000_000,
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
        # IMPORTANT: Only cache INITIAL complete SPS/PPS from stream start
        # Later SPS/PPS may be truncated across chunks
        self.cached_sps: bytes | None = None
        self.cached_pps: bytes | None = None
        self.cached_idr: bytes | None = None  # Last IDR frame for immediate playback
        self.sps_pps_locked = False  # Lock SPS/PPS after initial complete capture
        # Note: IDR is NOT locked - we keep updating to the latest frame

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
                "max_fps=20",  # ✅ Limit to 20fps to reduce data volume
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

        # Increase socket buffer size for high-resolution video
        # Default is often 64KB, but complex frames can be 200-500KB
        try:
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)  # 2MB
            print("[ScrcpyStreamer] Set socket receive buffer to 2MB")
        except OSError as e:
            print(f"[ScrcpyStreamer] Warning: Failed to set socket buffer size: {e}")

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
        """Parse and cache INITIAL complete NAL units (SPS, PPS, IDR).

        IMPORTANT: Only caches complete SPS/PPS from stream start.
        NAL units may be truncated across chunks, so we validate minimum sizes
        and lock the cache after getting complete initial parameters.
        """
        nal_units = self._find_nal_units(data)

        for start, nal_type, size in nal_units:
            nal_data = data[start:start+size]

            if nal_type == 7:  # SPS
                # Only cache SPS if not yet locked
                if not self.sps_pps_locked:
                    # Validate: SPS should be at least 10 bytes
                    if size >= 10 and not self.cached_sps:
                        self.cached_sps = nal_data
                        hex_preview = ' '.join(f'{b:02x}' for b in nal_data[:min(12, len(nal_data))])
                        print(f"[ScrcpyStreamer] ✓ Cached complete SPS ({size} bytes): {hex_preview}...")
                    elif size < 10:
                        print(f"[ScrcpyStreamer] ✗ Skipped truncated SPS ({size} bytes, too short)")

            elif nal_type == 8:  # PPS
                # Only cache PPS if not yet locked
                if not self.sps_pps_locked:
                    # Validate: PPS should be at least 6 bytes
                    if size >= 6 and not self.cached_pps:
                        self.cached_pps = nal_data
                        hex_preview = ' '.join(f'{b:02x}' for b in nal_data[:min(12, len(nal_data))])
                        print(f"[ScrcpyStreamer] ✓ Cached complete PPS ({size} bytes): {hex_preview}...")
                    elif size < 6:
                        print(f"[ScrcpyStreamer] ✗ Skipped truncated PPS ({size} bytes, too short)")

            elif nal_type == 5:  # IDR frame
                # ✅ ALWAYS update IDR to keep the LATEST frame
                # This gives better UX on reconnect (recent content, not stale startup frame)
                if self.cached_sps and self.cached_pps:
                    is_first = self.cached_idr is None
                    self.cached_idr = nal_data
                    if is_first:
                        print(f"[ScrcpyStreamer] ✓ Cached initial IDR frame ({size} bytes)")
                    # Don't log every IDR update (too verbose)

        # Lock SPS/PPS once we have complete initial parameters
        if self.cached_sps and self.cached_pps and not self.sps_pps_locked:
            self.sps_pps_locked = True
            print("[ScrcpyStreamer] 🔒 SPS/PPS locked (IDR will continue updating)")

    def _prepend_sps_pps_to_idr(self, data: bytes) -> bytes:
        """Prepend SPS/PPS before EVERY IDR frame unconditionally.

        This ensures that clients can start decoding from any IDR frame,
        even if they join mid-stream. We always prepend to guarantee
        that every IDR is self-contained.

        Returns:
            Modified data with SPS/PPS prepended to all IDR frames
        """
        if not self.cached_sps or not self.cached_pps:
            return data

        nal_units = self._find_nal_units(data)
        if not nal_units:
            return data

        # Find all IDR frames
        idr_positions = [(start, size) for start, nal_type, size in nal_units if nal_type == 5]

        if not idr_positions:
            return data

        # Build modified data by prepending SPS/PPS before each IDR
        result = bytearray()
        last_pos = 0
        sps_pps = self.cached_sps + self.cached_pps

        for idr_start, idr_size in idr_positions:
            # Add data before this IDR
            result.extend(data[last_pos:idr_start])

            # Check if SPS/PPS already exists right before this IDR
            # (to avoid duplicating if scrcpy already sent them)
            prepend_offset = max(0, idr_start - len(sps_pps))
            if data[prepend_offset:idr_start] != sps_pps:
                # Prepend SPS/PPS before this IDR
                result.extend(sps_pps)
                print(f"[ScrcpyStreamer] Prepended SPS/PPS before IDR at position {idr_start}")

            # Update position to start of IDR
            last_pos = idr_start

        # Add remaining data (including all IDR frames and data after)
        result.extend(data[last_pos:])

        return bytes(result)

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

            # Validate data integrity
            print(f"[ScrcpyStreamer] Returning init data:")
            print(f"  - SPS: {len(self.cached_sps)} bytes, starts with {' '.join(f'{b:02x}' for b in self.cached_sps[:8])}")
            print(f"  - PPS: {len(self.cached_pps)} bytes, starts with {' '.join(f'{b:02x}' for b in self.cached_pps[:8])}")
            if self.cached_idr:
                print(f"  - IDR: {len(self.cached_idr)} bytes, starts with {' '.join(f'{b:02x}' for b in self.cached_idr[:8])}")
            print(f"  - Total: {len(init_data)} bytes")

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
            # Read up to 512KB at once for high-quality frames
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self.tcp_socket.recv, 512 * 1024)

            if not data:
                raise ConnectionError("Socket closed by remote")

            # Log large chunks (might indicate complex frames)
            if len(data) > 200 * 1024:  # > 200KB
                print(f"[ScrcpyStreamer] Large chunk received: {len(data) / 1024:.1f} KB")

            # Cache INITIAL complete SPS/PPS/IDR for future use
            # (Later chunks may have truncated NAL units, so we only cache once)
            self._cache_nal_units(data)

            # NOTE: We don't automatically prepend SPS/PPS here because:
            # 1. NAL units may be truncated across chunks
            # 2. Prepending truncated SPS/PPS causes decoding errors
            # 3. Instead, we send cached complete SPS/PPS when new connections join

            return data
        except ConnectionError:
            raise
        except Exception as e:
            print(f"[ScrcpyStreamer] Unexpected error in read_h264_chunk: {type(e).__name__}: {e}")
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
