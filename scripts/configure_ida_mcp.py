#!/usr/bin/env python3
"""Atomically configure the headless IDA MCP server in Codex config.toml."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

import tomli_w


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Codex config.toml")
    parser.add_argument("--command", type=Path, required=True, help="idalib-mcp executable")
    parser.add_argument("--server-name", default="idalib", help="MCP server table name")
    args = parser.parse_args()

    config_path = args.config.resolve()
    command_path = args.command.resolve()
    if not config_path.is_file():
        raise SystemExit(f"Codex config not found: {config_path}")
    if not command_path.is_file():
        raise SystemExit(f"idalib-mcp executable not found: {command_path}")

    original = config_path.read_bytes()
    config = tomllib.loads(original.decode("utf-8"))
    servers = config.setdefault("mcp_servers", {})
    desired = {
        "command": str(command_path),
        "args": ["--stdio"],
        "startup_timeout_sec": 120,
    }
    if servers.get(args.server_name) == desired:
        print(f"MCP server '{args.server_name}' is already configured")
        return

    servers[args.server_name] = desired
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_path.with_name(f"{config_path.name}.bak-ida-mcp-{timestamp}")
    shutil.copy2(config_path, backup)

    rendered = tomli_w.dumps(config).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".config-ida-mcp-", suffix=".toml", dir=config_path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, config_path)
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise

    print(f"configured MCP server '{args.server_name}'")
    print(f"backup: {backup}")


if __name__ == "__main__":
    main()
