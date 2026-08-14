#!/usr/bin/env python3
"""Run a bounded, headless H1 QEMU probe and retain diagnostic logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path


H1_TOUCH_CROSS_RGB = (0x68, 0xB0, 0xF0)
H1_TOUCH_CALIBRATION_POINTS = (
    (20, 20, 0x0E74, 0x0DDE),
    (460, 20, 0x0177, 0x0DDE),
    (460, 252, 0x0172, 0x00F0),
    (20, 252, 0x0E60, 0x00F0),
)


def reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def connect_monitor(port: int, process: subprocess.Popen, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited before HMP became available: {process.returncode}")
        try:
            monitor = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            monitor.settimeout(0.25)
            return monitor
        except OSError as error:
            last_error = error
            time.sleep(0.1)
    raise TimeoutError(f"HMP did not listen on port {port}: {last_error}")


def connect_input(port: int, process: subprocess.Popen, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"QEMU exited before the input chardev became available: {process.returncode}"
            )
        try:
            input_socket = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            input_socket.settimeout(2.0)
            return input_socket
        except OSError as error:
            last_error = error
            time.sleep(0.1)
    raise TimeoutError(f"input chardev did not listen on port {port}: {last_error}")


def read_monitor_prompt(monitor: socket.socket, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while time.monotonic() < deadline:
        try:
            chunk = monitor.recv(4096)
        except TimeoutError:
            continue
        if not chunk:
            break
        output.extend(chunk)
        if b"(qemu)" in output:
            return output.decode("utf-8", errors="replace")
    raise TimeoutError(f"HMP prompt timeout; response={output.decode(errors='replace')!r}")


def monitor_command(monitor: socket.socket, command: str) -> str:
    monitor.sendall((command + "\r\n").encode("utf-8"))
    response = read_monitor_prompt(monitor)
    if "Error:" in response or "unknown command" in response.lower():
        raise RuntimeError(f"HMP command failed: {response.strip()}")
    return response


def wait_for_file(path: Path, process: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    previous = -1
    stable = 0
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            size = path.stat().st_size
            stable = stable + 1 if size == previous else 0
            previous = size
            if stable >= 2:
                return
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited before writing screenshot: {process.returncode}")
        time.sleep(0.1)
    raise TimeoutError(f"QEMU did not create screenshot {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def parse_memory_dump(value: str) -> tuple[int, int, Path]:
    try:
        address_text, size_text, path_text = value.split(":", 2)
        address = int(address_text, 0)
        size = int(size_text, 0)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "memory dump must be ADDRESS:SIZE:PATH"
        ) from error
    if address < 0 or address > 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("memory dump address must fit in 32 bits")
    if size <= 0:
        raise argparse.ArgumentTypeError("memory dump size must be positive")
    if not path_text:
        raise argparse.ArgumentTypeError("memory dump path must not be empty")
    return address, size, Path(path_text)


def parse_touch_sample(value: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(part, 0) for part in value.split(":"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "touch sample must be X:Y:RAW_X:RAW_Y"
        ) from error
    if len(values) != 4:
        raise argparse.ArgumentTypeError("touch sample must be X:Y:RAW_X:RAW_Y")
    if any(coordinate < 0 or coordinate > 0xFFFF for coordinate in values):
        raise argparse.ArgumentTypeError("touch sample values must fit in 16 bits")
    return values


def parse_touch_swipe(value: str) -> tuple[int, int, int, int, int, int, int, int]:
    try:
        values = tuple(int(part, 0) for part in value.split(":"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "touch swipe must be X1:Y1:RAW_X1:RAW_Y1:X2:Y2:RAW_X2:RAW_Y2"
        ) from error
    if len(values) != 8:
        raise argparse.ArgumentTypeError(
            "touch swipe must be X1:Y1:RAW_X1:RAW_Y1:X2:Y2:RAW_X2:RAW_Y2"
        )
    if any(coordinate < 0 or coordinate > 0xFFFF for coordinate in values):
        raise argparse.ArgumentTypeError("touch swipe values must fit in 16 bits")
    return values


def capture_screen(
    monitor: socket.socket,
    process: subprocess.Popen,
    png_path: Path,
) -> dict:
    from PIL import Image

    png_path.parent.mkdir(parents=True, exist_ok=True)
    ppm_path = png_path.with_name(png_path.name + ".capture.ppm")
    for path in (png_path, ppm_path):
        if path.exists():
            path.unlink()
    hmp_path = str(ppm_path).replace("\\", "/").replace('"', '\\"')
    monitor_command(monitor, f'screendump "{hmp_path}" -f ppm')
    wait_for_file(ppm_path, process)
    with Image.open(ppm_path) as source:
        image = source.convert("RGB")
        image.save(png_path, format="PPM" if png_path.suffix.lower() == ".ppm" else "PNG")
    ppm_path.unlink()

    width, height = image.size
    cross_pixels = []
    colors = image.getcolors(maxcolors=width * height)
    for y in range(height):
        for x in range(width):
            if image.getpixel((x, y)) == H1_TOUCH_CROSS_RGB:
                cross_pixels.append((x, y))
    if cross_pixels:
        left = min(point[0] for point in cross_pixels)
        top = min(point[1] for point in cross_pixels)
        right = max(point[0] for point in cross_pixels)
        bottom = max(point[1] for point in cross_pixels)
        bbox = [left, top, right, bottom]
        center = [(left + right) // 2, (top + bottom) // 2]
    else:
        bbox = None
        center = None
    return {
        "path": str(png_path),
        "bytes": png_path.stat().st_size,
        "sha256": sha256_file(png_path),
        "size": [width, height],
        "unique_colors": None if colors is None else len(colors),
        "cross_rgb": "#68B0F0",
        "cross_pixels": len(cross_pixels),
        "cross_bbox": bbox,
        "cross_center": center,
    }


def analyze_cross_near(
    png_path: Path,
    expected_x: int,
    expected_y: int,
    radius: int = 16,
) -> dict:
    from PIL import Image

    with Image.open(png_path) as source:
        image = source.convert("RGB")
    points = []
    for y in range(max(0, expected_y - radius), min(image.height, expected_y + radius + 1)):
        for x in range(max(0, expected_x - radius), min(image.width, expected_x + radius + 1)):
            if image.getpixel((x, y)) == H1_TOUCH_CROSS_RGB:
                points.append((x, y))
    return {
        "center": [expected_x, expected_y],
        "radius": radius,
        "pixels": len(points),
    }


def wait_for_touch_target(
    monitor: socket.socket,
    process: subprocess.Popen,
    png_path: Path,
    expected_x: int,
    expected_y: int,
    timeout: float,
) -> dict:
    deadline = time.monotonic() + timeout
    last_screen = None
    while time.monotonic() < deadline:
        last_screen = capture_screen(monitor, process, png_path)
        nearby = analyze_cross_near(png_path, expected_x, expected_y)
        last_screen["expected_cross"] = nearby
        if nearby["pixels"] >= 6:
            return last_screen
        if process.poll() is not None:
            raise RuntimeError(
                f"QEMU exited while waiting for touch target: {process.returncode}"
            )
        time.sleep(0.2)
    raise TimeoutError(
        f"touch target ({expected_x}, {expected_y}) did not appear; last={last_screen}"
    )


def run_touch_calibration(
    monitor: socket.socket,
    input_socket: socket.socket,
    process: subprocess.Popen,
    output_dir: Path,
    start_after: float,
    hold_seconds: float,
    settle_seconds: float,
    target_timeout: float,
    exit_timeout: float,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if start_after > 0:
        time.sleep(start_after)
    result = {
        "protocol": "T x y raw_x raw_y down",
        "points": [],
        "sequence_sent": False,
        "exited_calibration": False,
        "restarted": False,
    }
    for index, (x, y, raw_x, raw_y) in enumerate(H1_TOUCH_CALIBRATION_POINTS, 1):
        before = wait_for_touch_target(
            monitor,
            process,
            output_dir / f"point-{index}-before.png",
            x,
            y,
            target_timeout,
        )
        down_line = f"T {x} {y} {raw_x} {raw_y} 1"
        up_line = f"T {x} {y} {raw_x} {raw_y} 0"
        input_socket.sendall((down_line + "\n").encode("ascii"))
        time.sleep(hold_seconds)
        input_socket.sendall((up_line + "\n").encode("ascii"))
        result["points"].append(
            {
                "index": index,
                "target": [x, y],
                "raw": [raw_x, raw_y],
                "down": down_line,
                "up": up_line,
                "before": before,
            }
        )
        time.sleep(settle_seconds)
    result["sequence_sent"] = True

    deadline = time.monotonic() + exit_timeout
    first_x, first_y, _, _ = H1_TOUCH_CALIBRATION_POINTS[0]
    last_x, last_y, _, _ = H1_TOUCH_CALIBRATION_POINTS[-1]
    while time.monotonic() < deadline:
        after_path = output_dir / "after.png"
        screen = capture_screen(monitor, process, after_path)
        result["after"] = screen
        last_nearby = analyze_cross_near(after_path, last_x, last_y)
        first_nearby = analyze_cross_near(after_path, first_x, first_y)
        screen["last_target_cross"] = last_nearby
        screen["first_target_cross"] = first_nearby
        if last_nearby["pixels"] < 6 and first_nearby["pixels"] < 6:
            result["exited_calibration"] = True
            break
        if first_nearby["pixels"] >= 6:
            result["restarted"] = True
            break
        time.sleep(0.25)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--nand-image", type=Path)
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="route block writes to a temporary QEMU snapshot",
    )
    parser.add_argument("--runtime-bin", type=Path, action="append", default=[])
    parser.add_argument("--machine", default="bbkh1")
    parser.add_argument("--memory", default="64M")
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--log-prefix", type=Path, required=True)
    parser.add_argument("--trace", default="guest_errors,unimp")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--screenshot-after", type=float, default=10.0)
    parser.add_argument("--register-log", type=Path)
    parser.add_argument(
        "--memory-dump",
        type=parse_memory_dump,
        action="append",
        default=[],
        metavar="ADDRESS:SIZE:PATH",
        help="dump guest physical memory through HMP at the capture point",
    )
    parser.add_argument("--calibrate-touch", action="store_true")
    parser.add_argument("--calibration-dir", type=Path)
    parser.add_argument("--touch-start-after", type=float, default=4.0)
    parser.add_argument("--touch-hold", type=float, default=0.35)
    parser.add_argument("--touch-settle", type=float, default=0.65)
    parser.add_argument("--touch-target-timeout", type=float, default=15.0)
    parser.add_argument("--touch-exit-timeout", type=float, default=15.0)
    parser.add_argument(
        "--post-calibration-touch",
        type=parse_touch_sample,
        action="append",
        default=[],
        metavar="X:Y:RAW_X:RAW_Y",
    )
    parser.add_argument(
        "--post-calibration-swipe",
        type=parse_touch_swipe,
        action="append",
        default=[],
        metavar="X1:Y1:RAW_X1:RAW_Y1:X2:Y2:RAW_X2:RAW_Y2",
    )
    parser.add_argument("--post-calibration-touch-delay", type=float, default=1.0)
    args = parser.parse_args()

    qemu = args.qemu.resolve(strict=True)
    firmware = args.firmware.resolve(strict=True)
    nand_image = args.nand_image.resolve(strict=True) if args.nand_image else None
    prefix = args.log_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    uart_log = prefix.with_name(prefix.name + "-uart.log")
    qemu_log = prefix.with_name(prefix.name + "-qemu.log")
    stdout_log = prefix.with_name(prefix.name + "-stdout.log")
    stderr_log = prefix.with_name(prefix.name + "-stderr.log")
    screenshot = args.screenshot.resolve() if args.screenshot else None
    register_log = args.register_log.resolve() if args.register_log else None
    capture_path = screenshot
    if screenshot or register_log or args.memory_dump or args.calibrate_touch:
        if args.screenshot_after < 0 or args.screenshot_after >= args.seconds:
            parser.error("--screenshot-after must be non-negative and less than --seconds")
    if args.calibrate_touch and args.calibration_dir is None:
        parser.error("--calibration-dir is required with --calibrate-touch")
    for value, name in (
        (args.touch_start_after, "--touch-start-after"),
        (args.touch_hold, "--touch-hold"),
        (args.touch_settle, "--touch-settle"),
        (args.touch_target_timeout, "--touch-target-timeout"),
        (args.touch_exit_timeout, "--touch-exit-timeout"),
        (args.post_calibration_touch_delay, "--post-calibration-touch-delay"),
    ):
        if value < 0:
            parser.error(f"{name} must be non-negative")
    if register_log:
        register_log.parent.mkdir(parents=True, exist_ok=True)
        if register_log.exists():
            register_log.unlink()
    if screenshot:
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        if screenshot.exists():
            screenshot.unlink()
        if screenshot.suffix.lower() == ".png":
            capture_path = screenshot.with_name(screenshot.name + ".capture.ppm")
        elif screenshot.suffix.lower() != ".ppm":
            parser.error("--screenshot must end in .png or .ppm")
        if capture_path != screenshot and capture_path.exists():
            capture_path.unlink()

    env = os.environ.copy()
    runtime = [str(path.resolve(strict=True)) for path in args.runtime_bin]
    if runtime:
        env["PATH"] = os.pathsep.join(runtime + [env.get("PATH", "")])

    machine = args.machine
    monitor_port = (
        reserve_tcp_port()
        if screenshot or register_log or args.memory_dump or args.calibrate_touch
        else None
    )
    input_port = reserve_tcp_port() if args.calibrate_touch else None
    if input_port is not None:
        machine += ",input-chardev=h1-input"
    command = [
        str(qemu),
        "-machine",
        machine,
        "-m",
        args.memory,
        "-kernel",
        str(firmware),
        "-display",
        "none",
        "-monitor",
        (
            f"tcp:127.0.0.1:{monitor_port},server=on,wait=off"
            if monitor_port is not None
            else "none"
        ),
        "-serial",
        f"file:{uart_log}",
        "-d",
        args.trace,
        "-D",
        str(qemu_log),
    ]
    if nand_image is not None:
        nand_path = str(nand_image).replace("\\", "/")
        command.extend(
            [
                "-drive",
                f"if=mtd,index=0,format=raw,cache=writeback,file={nand_path}",
            ]
        )
    if args.snapshot:
        command.append("-snapshot")
    if input_port is not None:
        command.extend(
            [
                "-chardev",
                (
                    "socket,id=h1-input,host=127.0.0.1,"
                    f"port={input_port},server=on,wait=off,nodelay=on"
                ),
            ]
        )

    timed_out = False
    screenshot_result = None
    calibration_result = None
    with stdout_log.open("wb") as stdout, stderr_log.open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
        started = time.monotonic()
        monitor = None
        input_socket = None
        try:
            if monitor_port is not None:
                monitor = connect_monitor(monitor_port, process)
                read_monitor_prompt(monitor)
                if input_port is not None:
                    input_socket = connect_input(input_port, process)
                    assert args.calibration_dir is not None
                    calibration_result = run_touch_calibration(
                        monitor,
                        input_socket,
                        process,
                        args.calibration_dir.resolve(),
                        args.touch_start_after,
                        args.touch_hold,
                        args.touch_settle,
                        args.touch_target_timeout,
                        args.touch_exit_timeout,
                    )
                    calibration_result["post_touches"] = []
                    for x, y, raw_x, raw_y in args.post_calibration_touch:
                        time.sleep(args.post_calibration_touch_delay)
                        down_line = f"T {x} {y} {raw_x} {raw_y} 1"
                        up_line = f"T {x} {y} {raw_x} {raw_y} 0"
                        input_socket.sendall((down_line + "\n").encode("ascii"))
                        time.sleep(args.touch_hold)
                        input_socket.sendall((up_line + "\n").encode("ascii"))
                        calibration_result["post_touches"].append(
                            {
                                "screen": [x, y],
                                "raw": [raw_x, raw_y],
                                "down": down_line,
                                "up": up_line,
                            }
                        )
                    calibration_result["post_swipes"] = []
                    for (
                        x1,
                        y1,
                        raw_x1,
                        raw_y1,
                        x2,
                        y2,
                        raw_x2,
                        raw_y2,
                    ) in args.post_calibration_swipe:
                        time.sleep(args.post_calibration_touch_delay)
                        start_line = f"T {x1} {y1} {raw_x1} {raw_y1} 1"
                        move_line = f"T {x2} {y2} {raw_x2} {raw_y2} 1"
                        up_line = f"T {x2} {y2} {raw_x2} {raw_y2} 0"
                        input_socket.sendall((start_line + "\n").encode("ascii"))
                        time.sleep(args.touch_hold)
                        input_socket.sendall((move_line + "\n").encode("ascii"))
                        time.sleep(args.touch_hold)
                        input_socket.sendall((up_line + "\n").encode("ascii"))
                        calibration_result["post_swipes"].append(
                            {
                                "screen": [[x1, y1], [x2, y2]],
                                "raw": [[raw_x1, raw_y1], [raw_x2, raw_y2]],
                                "start": start_line,
                                "move": move_line,
                                "up": up_line,
                            }
                        )
                remaining = args.screenshot_after - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
                if screenshot is not None:
                    screenshot_result = capture_screen(monitor, process, screenshot)
                    screenshot_result["captured_after_seconds"] = (
                        time.monotonic() - started
                    )
                if register_log is not None:
                    register_log.write_text(
                        monitor_command(monitor, "info registers"), encoding="utf-8"
                    )
                for address, size, dump_path in args.memory_dump:
                    resolved_dump = dump_path.resolve()
                    resolved_dump.parent.mkdir(parents=True, exist_ok=True)
                    if resolved_dump.exists():
                        resolved_dump.unlink()
                    hmp_path = str(resolved_dump).replace("\\", "/").replace(
                        '"', '\\"'
                    )
                    monitor_command(
                        monitor,
                        f'pmemsave 0x{address:x} {size} "{hmp_path}"',
                    )
                    wait_for_file(resolved_dump, process)
                monitor.sendall(b"quit\r\n")
            remaining = max(0.1, args.seconds - (time.monotonic() - started))
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        finally:
            if monitor is not None:
                monitor.close()
            if input_socket is not None:
                input_socket.close()
            if capture_path != screenshot and capture_path is not None and capture_path.exists():
                capture_path.unlink()

    result = {
        "command": command,
        "pid": process.pid,
        "timed_out": timed_out,
        "exit_code": process.returncode,
        "logs": {
            "uart": {"path": str(uart_log), "bytes": uart_log.stat().st_size},
            "qemu": {"path": str(qemu_log), "bytes": qemu_log.stat().st_size},
            "stdout": {"path": str(stdout_log), "bytes": stdout_log.stat().st_size},
            "stderr": {"path": str(stderr_log), "bytes": stderr_log.stat().st_size},
        },
        "screenshot": screenshot_result,
        "calibration": calibration_result,
        "nand_backend": (
            None
            if nand_image is None
            else {
                "path": str(nand_image),
                "mode": "writable-mtd-block-backend",
                "sha256_after": sha256_file(nand_image),
            }
        ),
        "register_log": (
            None
            if register_log is None
            else {"path": str(register_log), "bytes": register_log.stat().st_size}
        ),
        "memory_dumps": [
            {
                "address": f"0x{address:08X}",
                "bytes": size,
                "path": str(path.resolve()),
                "sha256": sha256_file(path.resolve()),
            }
            for address, size, path in args.memory_dump
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
