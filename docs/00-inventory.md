# Source and environment inventory

Last updated: 2026-07-22 (Asia/Irkutsk)

## Original firmware archives

The workspace initially contained exactly two regular files and no Git
repository. The archives are preserved in place and will not be modified.

| File | Size (bytes) | SHA-256 | User-provided role |
| --- | ---: | --- | --- |
| `@ibox H1 V1.41CJXTHF.rar` | 467,351,318 | `B1F5F4D886C1C08C7D6F0722581615A7262CFE44B62F1F1E47EEF204F5E5E5DB` | PC-installed recovery/flashing package |
| `H1 V1.41SDKHF.rar` | 431,553,838 | `DFEA2563EF6770BA6E30E8006767DB6E7542C59D63CDECD05B266515D94A5A0C` | SD-card recovery package |

Status: **confirmed** by `Get-ChildItem` and `Get-FileHash -Algorithm SHA256`.

## Host tools

| Tool | Result | Status |
| --- | --- | --- |
| IDA Professional | `C:\Program Files\IDA Professional 9.3` | **confirmed installed** |
| 7-Zip | `C:\Program Files\7-Zip\7z.exe` | **confirmed installed** |
| Legacy `ida-pro-mcp.exe` | `C:\Program Files\Python314\Scripts\ida-pro-mcp.exe` | **v1.4.0, startup broken** |
| Current `idalib-mcp.exe` | `%USERPROFILE%\.local\bin\idalib-mcp.exe` | **v2.0.0, validated** |

The legacy global-Python entry points stop with `ModuleNotFoundError: No module
named 'typing_extensions'`. A separate current user-level installation is now
validated. See [02-ida-mcp.md](02-ida-mcp.md).

## Completed archive correlation

Both RAR archives have been extracted. The PC package's three encrypted
low-level payloads decrypt exactly to the SD package's `loader.bin`,
`u-boot.bin`, and `project.bin`; all 482 files in `packet1.dat` exactly match
the SD package's 482 `系统数据` files. See [03-firmware.md](03-firmware.md).
