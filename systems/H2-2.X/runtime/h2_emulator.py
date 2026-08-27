#!/usr/bin/env python3
"""Local noVNC frontend and QEMU process controller for BBK @ibox H2."""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


APP_DIR = Path(__file__).resolve().parent
ALLOWED_KEYS = {
    "left",
    "right",
    "ret",
    "esc",
    "volumedown",
    "volumeup",
    "power",
}


def first_candidate(*paths: str) -> Path:
    candidates = [APP_DIR / path for path in paths]
    return next((path for path in candidates if path.exists()), candidates[0])


def reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def reserve_vnc_display() -> tuple[int, int]:
    for display in range(20, 100):
        port = 5900 + display
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return display, port
    raise RuntimeError("no free local VNC display in the range :20 through :99")


def wait_for_port(port: int, process: subprocess.Popen[bytes], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited during startup with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise TimeoutError(f"QEMU port {port} did not open: {last_error}")


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("VNC server closed the connection")
        data.extend(chunk)
    return bytes(data)


def send_vnc_tap(port: int, x: int, y: int, hold_seconds: float = 0.55) -> None:
    """Send one absolute touchscreen tap without depending on browser state."""

    with socket.create_connection(("127.0.0.1", port), timeout=3.0) as sock:
        sock.settimeout(3.0)
        version = recv_exact(sock, 12)
        if not version.startswith(b"RFB 003."):
            raise RuntimeError(f"unexpected VNC banner: {version!r}")
        sock.sendall(b"RFB 003.008\n")
        security_count = recv_exact(sock, 1)[0]
        if security_count == 0:
            reason_size = struct.unpack(">I", recv_exact(sock, 4))[0]
            reason = recv_exact(sock, reason_size).decode("utf-8", "replace")
            raise RuntimeError(f"VNC security negotiation failed: {reason}")
        security_types = recv_exact(sock, security_count)
        if 1 not in security_types:
            raise RuntimeError("local VNC server does not offer no-auth access")
        sock.sendall(b"\x01")
        if struct.unpack(">I", recv_exact(sock, 4))[0] != 0:
            raise RuntimeError("VNC security negotiation was rejected")
        sock.sendall(b"\x01")
        width, height = struct.unpack(">HH", recv_exact(sock, 4))
        recv_exact(sock, 16)
        name_size = struct.unpack(">I", recv_exact(sock, 4))[0]
        recv_exact(sock, name_size)
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError(f"tap ({x},{y}) is outside {width}x{height}")
        # QEMU otherwise treats this minimal RFB client as a relative mouse and
        # reuses a stale cursor coordinate. PointerTypeChange selects the H2
        # Ingenic absolute touchscreen before the button pair is submitted.
        sock.sendall(struct.pack(">BBHii", 2, 0, 2, 0, -257))
        sock.sendall(struct.pack(">BBHH", 5, 1, x, y))
        time.sleep(hold_seconds)
        sock.sendall(struct.pack(">BBHH", 5, 0, x, y))


class H2Runtime:
    def __init__(
        self,
        qemu: Path,
        bios: Path,
        emmc: Path,
        keymap: Path,
        snapshot: bool,
        qemu_log: Path | None = None,
        auto_resume: bool = False,
        auto_mission_page: bool = False,
        mission_page_delay: float = 30.0,
        gdb_port: int | None = None,
    ) -> None:
        self.qemu = qemu.resolve()
        self.bios = bios.resolve()
        self.emmc = emmc.resolve()
        self.keymap = keymap.resolve()
        self.snapshot = snapshot
        self.qemu_log = qemu_log.resolve() if qemu_log is not None else None
        self.auto_resume = auto_resume
        self.auto_mission_page = auto_mission_page
        self.mission_page_delay = mission_page_delay
        self.gdb_port = gdb_port
        self.mission_page_navigation = "disabled"
        self.compatibility_auto_resumes = 0
        self.process: subprocess.Popen[bytes] | None = None
        self.vnc_display: int | None = None
        self.monitor_port: int | None = None
        self.websocket_port: int | None = None
        self.vnc_port: int | None = None
        self.command: list[str] = []
        self.started_at: float | None = None
        self.stop_event = threading.Event()
        self.monitor_lock = threading.Lock()
        self.lifecycle_lock = threading.RLock()
        self.last_returncode: int | None = None
        self.last_error: str | None = None

    def validate(self) -> None:
        for label, path in (
            ("QEMU", self.qemu),
            ("JZ4750L bootrom", self.bios),
            ("H2 eMMC image", self.emmc),
            ("H2 key map", self.keymap),
        ):
            if not path.is_file():
                raise FileNotFoundError(f"{label} not found: {path}")
        if self.emmc.stat().st_size != 2 * 1024 * 1024 * 1024:
            raise ValueError("the H2 eMMC image must be exactly 2 GiB")

    def start(self) -> None:
        with self.lifecycle_lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("QEMU is already running")
            if self.process is not None:
                self._record_process_exit(self.process)
                self.process = None
            self.validate()
            if self.vnc_display is None or self.vnc_port is None:
                self.vnc_display, self.vnc_port = reserve_vnc_display()
            if self.websocket_port is None:
                self.websocket_port = reserve_tcp_port()
            if self.monitor_port is None:
                self.monitor_port = reserve_tcp_port()
            display = self.vnc_display
        emmc_posix = self.emmc.as_posix()
        keymap_posix = self.keymap.as_posix()
        self.command = [
            str(self.qemu),
            "-machine",
            "bbk_iboxh2",
            "-bios",
            str(self.bios),
            "-L",
            str(APP_DIR / "share" / "qemu"),
            "-accel",
            "tcg,thread=single,tb-size=256",
            "-drive",
            f"if=none,id=emmc0,format=raw,file={emmc_posix}",
            "-device",
            "emmc,drive=emmc0,bus=sd-bus-msc0",
            "-global",
            f"gpio-matrix-keypad.map-file={keymap_posix}",
            "-global",
            "ingenic-rtc.hspr=0x12345678",
            "-display",
            "none",
            "-vnc",
            f"127.0.0.1:{display},websocket={self.websocket_port}",
            "-monitor",
            f"tcp:127.0.0.1:{self.monitor_port},server=on,wait=off",
            "-serial",
            "none",
            "-no-reboot",
        ]
        if self.gdb_port is not None:
            self.command.extend(["-gdb", f"tcp:127.0.0.1:{self.gdb_port}"])
        if self.snapshot:
            self.command.append("-snapshot")
        if self.qemu_log is not None:
            self.qemu_log.parent.mkdir(parents=True, exist_ok=True)
            self.command.extend(
                ["-d", "unimp,guest_errors", "-D", str(self.qemu_log)]
            )
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join((str(self.qemu.parent), env.get("PATH", "")))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            self.command,
            cwd=str(APP_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        process = self.process
        self.last_returncode = None
        self.last_error = None
        self.started_at = time.monotonic()
        try:
            wait_for_port(self.monitor_port, process)
            wait_for_port(self.websocket_port, process)
            if self.auto_resume:
                threading.Thread(
                    target=self._compatibility_pause_loop,
                    args=(process,),
                    name="h2-qemu-pause-compat",
                    daemon=True,
                ).start()
            if self.auto_mission_page:
                self.mission_page_navigation = "waiting-for-desktop"
                threading.Thread(
                    target=self._mission_page_navigation_loop,
                    args=(process,),
                    name="h2-mission-page-navigation",
                    daemon=True,
                ).start()
        except Exception as error:
            details = ""
            if self.process.poll() is not None and self.process.stderr is not None:
                details = self.process.stderr.read().decode("utf-8", "replace").strip()
            self.stop_process()
            suffix = f": {details[-2000:]}" if details else ""
            raise RuntimeError(f"{error}{suffix}") from error

    def hmp(self, command: str) -> str:
        if self.process is None or self.process.poll() is not None or self.monitor_port is None:
            raise RuntimeError("QEMU is not running")
        with self.monitor_lock, socket.create_connection(
            ("127.0.0.1", self.monitor_port), timeout=2.0
        ) as sock:
            sock.settimeout(2.0)
            banner = bytearray()
            while b"(qemu)" not in banner:
                banner.extend(sock.recv(4096))
            sock.sendall(command.encode("ascii") + b"\n")
            output = bytearray()
            while b"(qemu)" not in output:
                output.extend(sock.recv(4096))
            return output.decode("utf-8", "replace")

    def _compatibility_pause_loop(self, process: subprocess.Popen[bytes]) -> None:
        """Resume debug-style pauses caused by incomplete H2 device models."""
        while not self.stop_event.wait(0.1):
            if self.process is not process or process.poll() is not None:
                return
            try:
                if "VM status: paused" in self.hmp("info status"):
                    self.hmp("cont")
                    self.compatibility_auto_resumes += 1
            except (OSError, RuntimeError, TimeoutError):
                if process.poll() is not None:
                    return

    def _mission_page_navigation_loop(self, process: subprocess.Popen[bytes]) -> None:
        """Follow the fixed native UI path and stop on Mission's icon page."""

        if self.stop_event.wait(self.mission_page_delay):
            return
        if self.process is not process or process.poll() is not None or self.vnc_port is None:
            return
        try:
            # H2 briefly displays the launcher while touch dispatch is still
            # blocked by a post-boot task.  Its dead interval is about five
            # seconds; keep a fixed six-second guard before the first input.
            if self.stop_event.wait(6.0):
                return
            # Match the proven H1 V2 navigation sequence.  The clipped
            # Tools/Entertainment tab does not reliably accept a direct hit
            # while Dictionary is selected, so select its adjacent tab first.
            # H2 has two Tools/Entertainment pages.  Re-selecting the tab
            # above normalizes it to page one, and one deliberate page-down
            # selection reaches the final page containing Mission's clock.
            for _press in range(5):
                self.send_key("esc")
                if self.stop_event.wait(1.2):
                    return
            steps = (
                ("more-functions", ((420, 258),), 2.5),
                (
                    "adjacent-category",
                    ((380, 258), (390, 258)),
                    1.5,
                ),
                (
                    "tools-entertainment",
                    ((430, 258), (440, 258)),
                    1.5,
                ),
                (
                    "mission-page-1",
                    ((455, 216),),
                    3.0,
                ),
            )
            for state, points, settle_seconds in steps:
                if self.process is not process or process.poll() is not None:
                    return
                for attempt, (x, y) in enumerate(points, 1):
                    send_vnc_tap(self.vnc_port, x, y)
                    self.mission_page_navigation = f"{state}-{attempt}"
                    if state.startswith("mission-page"):
                        if self.stop_event.wait(0.3):
                            return
                        self.send_key("ret")
                    if self.stop_event.wait(0.8):
                        return
                if self.stop_event.wait(settle_seconds):
                    return
            self.mission_page_navigation = "ready"
        except (ConnectionError, OSError, RuntimeError, ValueError) as error:
            self.mission_page_navigation = f"failed: {error}"

    def send_key(self, key: str, duration_ms: int = 120) -> None:
        if key not in ALLOWED_KEYS:
            raise ValueError(f"unsupported H2 key: {key}")
        duration_ms = max(80, min(int(duration_ms), 2000))
        self.hmp(f"sendkey {key} {duration_ms}")
        # OpenNoah's H2 model changes the real PC1/PC3 pin levels but can lose
        # their interrupt wake once a foreign V1 event loop is active.  Pulse a
        # known-working H2 volume IRQ a little later; the H2 Mission shim reads
        # PC1/PC3 directly and consumes this pulse only as a wakeup.  Native H2
        # applications still receive the unmodified seven-key device model.
        if key in ("left", "right"):
            wake_key = "volumedown" if key == "left" else "volumeup"
            self.hmp(f"sendkey {wake_key} {min(duration_ms + 30, 2000)}")

    def send_tap(self, x: int, y: int, hold_ms: int = 550) -> None:
        if self.vnc_port is None:
            raise RuntimeError("QEMU did not publish a VNC port")
        if not 0 <= int(x) < 480 or not 0 <= int(y) < 272:
            raise ValueError("tap must stay inside the 480x272 H2 display")
        hold_ms = max(80, min(int(hold_ms), 2000))
        send_vnc_tap(self.vnc_port, int(x), int(y), hold_ms / 1000.0)

    def debug_memory(self, address: int, count: int) -> str:
        """Read a small, bounded physical-RAM window through QEMU HMP."""
        if address & 3:
            raise ValueError("debug address must be 4-byte aligned")
        if count < 1 or count > 256:
            raise ValueError("debug word count must be between 1 and 256")
        if address < 0 or address + count * 4 > 32 * 1024 * 1024:
            raise ValueError("debug range must stay inside H2's 32 MiB SDRAM")
        return self.hmp(f"xp /{count}wx 0x{address:08x}")

    def status(self) -> dict[str, Any]:
        # The HTTP handler and the main health loop can query status while a
        # restart is reaping the old process.  Serialize that path so stderr is
        # never read or closed concurrently by two threads.
        with self.lifecycle_lock:
            process = self.process
            returncode = process.poll() if process is not None else self.last_returncode
            running = process is not None and returncode is None
            if process is not None and returncode is not None:
                self._record_process_exit(process)
            return {
                "running": running,
                "returncode": returncode,
                "snapshot": self.snapshot,
                "websocketPort": self.websocket_port,
                "vncPort": self.vnc_port,
                "gdbPort": self.gdb_port,
                "uptimeSeconds": (
                    round(time.monotonic() - self.started_at, 1)
                    if running and self.started_at is not None
                    else None
                ),
                "compatibilityAutoResumes": self.compatibility_auto_resumes,
                "missionPageNavigation": self.mission_page_navigation,
                "lastError": self.last_error,
            }

    def _record_process_exit(self, process: subprocess.Popen[bytes]) -> None:
        returncode = process.poll()
        if returncode is None:
            return
        self.last_returncode = returncode
        details = ""
        if process.stderr is not None and not process.stderr.closed:
            details = process.stderr.read().decode("utf-8", "replace").strip()
            process.stderr.close()
        self.last_error = f"QEMU exited with code {returncode}"
        if details:
            self.last_error += f": {details[-2000:]}"

    def stop_process(self) -> None:
        with self.lifecycle_lock:
            process = self.process
            if process is None:
                return
            if process.poll() is None:
                try:
                    self.hmp("quit")
                    process.wait(timeout=3.0)
                except Exception:
                    process.terminate()
                    try:
                        process.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3.0)
            self._record_process_exit(process)
            self.process = None
            self.started_at = None

    def restart(self) -> None:
        with self.lifecycle_lock:
            self.stop_process()
            self.start()

    def shutdown(self) -> None:
        self.stop_event.set()
        self.stop_process()


def make_handler(runtime: H2Runtime, web_root: Path) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(web_root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.path = "/h2.html"
                super().do_GET()
                return
            if parsed.path == "/api/status":
                self.send_json(runtime.status())
                return
            if parsed.path == "/api/debug/memory":
                try:
                    query = parse_qs(parsed.query)
                    address = int(query.get("address", [""])[0], 0)
                    count = int(query.get("count", [""])[0], 0)
                    self.send_json(
                        {
                            "address": f"0x{address:08X}",
                            "count": count,
                            "memory": runtime.debug_memory(address, count),
                        }
                    )
                except (IndexError, ValueError, RuntimeError, OSError) as error:
                    self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            size = int(self.headers.get("Content-Length", "0"))
            try:
                request = json.loads(self.rfile.read(size) or b"{}")
                if path == "/api/key":
                    runtime.send_key(str(request.get("key", "")), int(request.get("duration", 120)))
                    self.send_json({"ok": True})
                    return
                if path == "/api/tap":
                    runtime.send_tap(
                        int(request.get("x", -1)),
                        int(request.get("y", -1)),
                        int(request.get("hold", 550)),
                    )
                    self.send_json({"ok": True})
                    return
                if path in ("/api/reset", "/api/restart"):
                    runtime.restart()
                    self.send_json({"ok": True})
                    return
                if path == "/api/start":
                    runtime.start()
                    self.send_json({"ok": True})
                    return
                if path == "/api/stop":
                    self.send_json({"ok": True})
                    threading.Thread(target=runtime.stop_process, daemon=True).start()
                    return
                self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, RuntimeError, OSError) as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qemu",
        type=Path,
        default=first_candidate(
            "bin/windows-arm64/qemu-system-mipsel.exe",
            "bin/qemu-system-mipsel.exe",
        ),
    )
    parser.add_argument("--bios", type=Path, default=first_candidate("firmware/jz4750l.bin"))
    parser.add_argument(
        "--emmc",
        type=Path,
        default=first_candidate("firmware/h2-v2.2l-emmc.raw"),
    )
    parser.add_argument("--keymap", type=Path, default=first_candidate("h2.keys"))
    parser.add_argument("--web-root", type=Path, default=first_candidate("web"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8797)
    parser.add_argument("--persistent", action="store_true", help="write changes to the eMMC image")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--qemu-log", type=Path, help="optional diagnostic QEMU log")
    parser.add_argument(
        "--gdb-port",
        type=int,
        help="optional localhost GDB server port for non-invasive diagnostics",
    )
    parser.add_argument(
        "--auto-resume-unsupported",
        action="store_true",
        help="diagnostic only: resume pauses requested by incomplete H2 device models",
    )
    parser.add_argument(
        "--mission-page",
        action="store_true",
        help="after boot, follow the fixed native UI path to Mission's icon page",
    )
    parser.add_argument(
        "--mission-page-delay",
        type=float,
        default=35.0,
        help="seconds to wait for the native desktop before --mission-page taps",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 5.0 <= args.mission_page_delay <= 120.0:
        print("error: --mission-page-delay must be between 5 and 120 seconds", file=sys.stderr)
        return 1
    if args.gdb_port is not None and not 1 <= args.gdb_port <= 65535:
        print("error: --gdb-port must be between 1 and 65535", file=sys.stderr)
        return 1
    runtime = H2Runtime(
        args.qemu,
        args.bios,
        args.emmc,
        args.keymap,
        not args.persistent,
        args.qemu_log,
        args.auto_resume_unsupported,
        args.mission_page,
        args.mission_page_delay,
        args.gdb_port,
    )
    server: ThreadingHTTPServer | None = None
    try:
        runtime.start()
        if runtime.websocket_port is None:
            raise RuntimeError("QEMU did not publish a WebSocket port")
        handler = make_handler(runtime, args.web_root.resolve())
        if not 1 <= args.port <= 65535:
            raise ValueError("HTTP port must be between 1 and 65535")
        server = ThreadingHTTPServer((args.host, args.port), handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        url = f"http://{args.host}:{int(server.server_address[1])}/"
        print("BBK H2 V2.2L simulator is running")
        print(url)
        print("Use the page's Stop button or press Ctrl+C here to exit.")
        if not args.no_browser:
            webbrowser.open(url)
        while not runtime.stop_event.wait(0.25):
            runtime.status()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        runtime.shutdown()
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
