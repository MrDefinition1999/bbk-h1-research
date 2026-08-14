# IDA Pro MCP setup and validation

Last updated: 2026-07-22 (Asia/Irkutsk)

## Initial observed state

- IDA Professional 9.3 is installed at
  `C:\Program Files\IDA Professional 9.3`.
- Python console launchers `ida-pro-mcp.exe` and `idalib-mcp.exe` exist under
  `C:\Program Files\Python314\Scripts`.
- Both launchers fail before argument parsing because `typing_extensions` is
  missing from that Python installation.
- The current user's Codex configuration contained a `node_repl` MCP server,
  but no IDA MCP server entry.
- The current Codex tool inventory exposes no IDA analysis tools or resources.

Conclusion at discovery time: the legacy installation was not operational.

## Current validated installation

Upstream commit: `120ae7abd871bd32d6002d5f9c4233a26ecdfd65`.

`uv tool install` installed a separate user-level `ida-pro-mcp 2.0.0` with
`idapro 0.0.10` and `tomli-w 1.2.0`. Its entry points are under
`%USERPROFILE%\.local\bin`. The legacy Python 3.14 installation is left
in place for now so no unrelated global package is removed.

The headless server was started on `127.0.0.1:8745` and passed:

1. MCP initialize negotiation (server selected protocol `2025-06-18`);
2. schema-worker startup and enumeration of 65 tools;
3. IDB open, automatic analysis, string cache, and Hex-Rays initialization;
4. binary survey, function listing, decompilation, and cross-reference queries;
5. comment insertion, function rename, type update, IDB save, and readback.

The validation fixture reported `auto_analysis_ready=true`,
`hexrays_ready=true`, and `strings_cache_ready=true`. The saved test database
is generated under `work/ida-test/`.

The legacy GUI link `mcp-plugin.py` was removed by the upstream installer and
replaced with the 2.0.0 `ida_mcp.py` loader and `ida_mcp` package. Codex
The Codex configuration now contains a headless `mcp_servers.idalib` entry using
`%USERPROFILE%\.local\bin\idalib-mcp.exe --stdio` with a 120-second
startup timeout. The previous config is preserved as
`config.toml.bak-ida-mcp-20260722-224559`.

## Validation target

The setup is considered working only after all of the following pass:

Items 1 through 4 are complete. Installation and configuration are also
complete. A Codex/IDA restart is still required before the newly configured
server and GUI plugin can be observed inside fresh application sessions; the
server itself has already been validated directly over MCP.

The configuration helper is
[`../scripts/configure_ida_mcp.py`](../scripts/configure_ida_mcp.py). It makes a
timestamped backup before atomically updating `config.toml`.
