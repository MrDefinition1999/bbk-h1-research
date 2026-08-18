#!/usr/bin/env python3
"""Call a local ida-pro-mcp streamable HTTP endpoint."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def decode_response(data: bytes) -> dict:
    text = data.decode("utf-8")
    if text.lstrip().startswith("data:"):
        lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not lines:
            raise ValueError("MCP returned an empty event stream")
        text = lines[-1]
    return json.loads(text)


class McpClient:
    def __init__(self, url: str):
        self.url = url
        self.session_id: str | None = None
        self.request_id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "id": self.request_id, "method": method}
        if params is not None:
            payload["params"] = params
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            session_id = response.headers.get("Mcp-Session-Id")
            if session_id:
                self.session_id = session_id
            body = decode_response(response.read())
        if "error" in body:
            raise RuntimeError(json.dumps(body["error"], ensure_ascii=False))
        return body["result"]

    def initialize(self) -> dict:
        return self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bbk-h1-research", "version": "1.0"},
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8745/mcp")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--structured", action="store_true", help="Print structuredContent only"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("tools", help="List MCP tools")
    call_parser = subparsers.add_parser("call", help="Call an MCP tool")
    call_parser.add_argument("name")
    call_parser.add_argument("arguments", nargs="?", default=None)
    call_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Add an argument; VALUE is parsed as JSON when possible",
    )
    args = parser.parse_args()

    client = McpClient(args.url)
    client.initialize()
    if args.command == "tools":
        result = client.request("tools/list")
    else:
        arguments = json.loads(args.arguments) if args.arguments else {}
        for assignment in args.arg:
            if "=" not in assignment:
                parser.error(f"invalid --arg value: {assignment!r}")
            key, value = assignment.split("=", 1)
            try:
                arguments[key] = json.loads(value)
            except json.JSONDecodeError:
                arguments[key] = value
        result = client.request(
            "tools/call",
            {"name": args.name, "arguments": arguments},
        )

    printable = result.get("structuredContent", result) if args.structured else result
    text = json.dumps(printable, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
