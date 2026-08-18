#!/usr/bin/env python3
"""Record local QEMU GDB write-watchpoint hits without a GDB installation."""

from __future__ import annotations

import argparse
import socket
import struct
import time


class RspClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(10)

    def close(self) -> None:
        self.sock.close()

    @staticmethod
    def _packet(payload: str) -> bytes:
        encoded = payload.encode("ascii")
        checksum = sum(encoded) & 0xFF
        return b"$" + encoded + f"#{checksum:02x}".encode("ascii")

    def _wait_for_ack(self) -> None:
        while True:
            marker = self.sock.recv(1)
            if marker == b"+":
                return
            if marker == b"-":
                raise RuntimeError("QEMU rejected an RSP packet checksum")
            if not marker:
                raise EOFError("QEMU closed the GDB connection")

    def _receive_packet(self) -> str:
        while True:
            marker = self.sock.recv(1)
            if not marker:
                raise EOFError("QEMU closed the GDB connection")
            if marker != b"$":
                continue
            payload = bytearray()
            while True:
                byte = self.sock.recv(1)
                if not byte:
                    raise EOFError("QEMU closed an incomplete RSP packet")
                if byte == b"#":
                    break
                payload.extend(byte)
            checksum_text = self.sock.recv(2)
            if len(checksum_text) != 2:
                raise EOFError("QEMU closed an incomplete RSP checksum")
            expected = int(checksum_text, 16)
            actual = sum(payload) & 0xFF
            self.sock.sendall(b"+" if actual == expected else b"-")
            if actual == expected:
                return payload.decode("ascii", errors="replace")

    def command(self, payload: str) -> str:
        self.sock.sendall(self._packet(payload))
        self._wait_for_ack()
        return self._receive_packet()

    def resume_until_stop(self, command: str, timeout: float) -> tuple[str, bool]:
        self.sock.sendall(self._packet(command))
        self._wait_for_ack()
        self.sock.settimeout(timeout)
        try:
            return self._receive_packet(), False
        except TimeoutError:
            self.sock.sendall(b"\x03")
            self.sock.settimeout(10)
            return self._receive_packet(), True


def decode_target_u32(value: str) -> int | None:
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return None
    if len(raw) != 4:
        return None
    return struct.unpack("<I", raw)[0]


def read_register(client: RspClient, number: int) -> int | None:
    return decode_target_u32(client.command(f"p{number:x}"))


def read_words(client: RspClient, address: int, count: int) -> list[int]:
    payload = client.command(f"m{address:x},{count * 4:x}")
    try:
        raw = bytes.fromhex(payload)
    except ValueError:
        return []
    if len(raw) != count * 4:
        return []
    return list(struct.unpack(f"<{count}I", raw))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--address", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--length", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-hits", type=int, default=8)
    parser.add_argument("--stack-words", type=int, default=0)
    args = parser.parse_args()

    client = RspClient(args.host, args.port)
    try:
        supported = client.command("qSupported:multiprocess+;swbreak+;hwbreak+")
        watch = client.command(f"Z2,{args.address:x},{args.length:x}")
        if watch != "OK":
            raise SystemExit(f"QEMU rejected the write watchpoint: {watch}")
        print(f"watch=0x{args.address:08x} supported={supported}", flush=True)

        started = time.monotonic()
        for index in range(args.max_hits):
            remaining = max(0.1, args.timeout - (time.monotonic() - started))
            stop, interrupted = client.resume_until_stop("c", remaining)
            step_stop = ""
            if not interrupted and "watch:" in stop:
                removed = client.command(f"z2,{args.address:x},{args.length:x}")
                if removed != "OK":
                    raise RuntimeError(f"failed to remove watchpoint: {removed}")
                step_stop, step_interrupted = client.resume_until_stop("s", 5.0)
                interrupted = interrupted or step_interrupted
            pc = read_register(client, 37)
            a0 = read_register(client, 4)
            s0 = read_register(client, 16)
            s1 = read_register(client, 17)
            sp = read_register(client, 29)
            ra = read_register(client, 31)
            value = decode_target_u32(
                client.command(f"m{args.address:x},{args.length:x}")
            )
            pc_text = "unknown" if pc is None else f"0x{pc:08x}"
            value_text = "unknown" if value is None else f"0x{value:08x}"
            reason = "timeout-interrupt" if interrupted else "watchpoint"
            print(
                f"hit={index + 1} reason={reason} pc={pc_text} "
                f"value={value_text} a0={a0!r} s0={s0!r} s1={s1!r} "
                f"sp={sp!r} ra={ra!r} stop={stop} step={step_stop}",
                flush=True,
            )
            if args.stack_words and sp is not None:
                words = read_words(client, sp, args.stack_words)
                print(
                    "stack=" + " ".join(f"{word:08x}" for word in words),
                    flush=True,
                )
            if interrupted or stop.startswith(("W", "X")):
                break
            restored = client.command(f"Z2,{args.address:x},{args.length:x}")
            if restored != "OK":
                raise RuntimeError(f"failed to restore watchpoint: {restored}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
