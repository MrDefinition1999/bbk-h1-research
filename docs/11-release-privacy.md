# Release privacy and artifact hygiene

Status: **confirmed policy**, 2026-07-30.

No public or handoff package may contain a local username, computer name,
user-profile path, workspace absolute path, Codex configuration path,
credential, token, or private key. Runtime logs, debugger logs, deployment
reports, Python bytecode caches, and nested Git reflogs are development data
and are not release inputs.

The MIPS SDK maps source and temporary build paths at compile time. QEMU release
executables are stripped and passed through the checked-in fixed-length binary
path sanitizer. Release archives and their decompressed entries are checked by:

```powershell
python scripts/audit_release_secrets.py
```

Any finding blocks release. The audit must be repeated after packaging because
checking the staging directory alone does not prove that the archive is clean.

The native ARM64 QEMU candidate has a separate reproducible finalization gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/finalize_arm64_qemu_release.ps1
```

The script rejects non-ARM64 PE input, runs the ARM64-capable LLVM strip tool,
applies the fixed-length path sanitizer, and audits both QEMU and the optimized
KOV BDA. A manually sanitized executable is not a release artifact.

Generated Python caches, runtime logs and development-only deployment/A-B
reports are removed reproducibly before the repository-wide audit:

```powershell
python scripts/cleanup_release_transients.py
python scripts/audit_release_secrets.py
```

## Audit coverage

The default audit covers the real-hardware deliverables (including every ZIP
entry), the Windows x86-64 emulator, the SDK build outputs, and the public
documentation. It recognizes ASCII and UTF-16 identity strings, slash and
JSON-escaped path forms, common API/token formats, and private-key headers.

Current build-machine identity always blocks a release. Generic profile paths
also block unless the user component is an explicit upstream placeholder or
public documentation sample such as `user`, `username`, or `example`. A URL
path segment and an example `DESKTOP-*` name are not treated as evidence of a
local identity. These distinctions are covered by checked-in unit tests.

## Validation record: 2026-07-30

- `python scripts/audit_release_secrets.py` checked 4,538 files and reported
  `findings=0`. ZIP contents were inspected from the archive, not inferred from
  the staging directory.
- The privacy detector's seven regression tests and the SDK's six build/path
  mapping tests passed.
- IDA database files, Python bytecode caches, runtime logs, audit scratch files,
  and release-candidate scratch binaries were removed.
- An obsolete DOOM test deployment was found in the live FAT file named
  `雷霆战机.bda`. It contained two old compiler paths. The file was restored to
  the original 148,512-byte application, SHA-256
  `8FAF28BD20EF92302EB045E199D730B57963BDCB0B6398173CC26FC3226C024D`.
  The final DOOM application remains independently installed and unchanged.
- Both NAND copies have 3,857 selected FTL mappings and no bad, invalid, or torn
  records. Their common SHA-256 is
  `FBCCAB7DA9C6DF8F790366E5756EBDE4345B4231FF249D155F40EBA38D534068`.
- The rebuilt x86-64 QEMU is 10,525,184 bytes, exposes the A320 asset bridge,
  charger state, and guest instruction counter, and has SHA-256
  `19BD3FE4F233C56D817D15083534A78E55808D3EA23BB97880C69E47810BBA39`.
  A launch smoke test reached completed automatic calibration, produced an
  RGBA8888 frame, advanced guest instructions, reported no runtime error, and
  stopped normally through the API.
- The real-hardware ZIP SHA-256 is
  `5595B7FDAFBC41B83F993381145B9A4162E07DEB41857FB74089918D5F7CA45F`.
  `scripts/refresh_real_hardware_release.py` synchronized all 18 verified game
  builds, generated 36 `A-root` checksums, created a fixed-timestamp ZIP, and
  passed both the 38-file staging audit and the archive-entry audit.
  The final DOOM BDA SHA-256 is
  `5B1D42F4588EE4F11028AC5154DA5DC8BE6833138214E1279B7A2C997412E7F8`.
- The non-release ARM64 QEMU candidate was audited separately and reported zero
  findings; it is not included in an x86-64 delivery package.

## ARM64 KOV performance candidate: 2026-08-01

- `scripts/finalize_arm64_qemu_release.ps1` verified PE machine `0xAA64`, ran
  ARM64 LLVM `--strip-all`, reduced QEMU from 13,887,488 to 10,854,400 bytes,
  and replaced 156 embedded build-machine path occurrences without changing
  string lengths.
- The finalized ARM64 QEMU SHA-256 is
  `2C09CE8C7C8752903057AD47BC3682DB142A71625CF2484DD9822FB0039AAA18`.
  The paired emulator KOV BDA SHA-256 is
  `0647E02FAA415A5DEF8B3FA48E231F50E1E8D1EF6550E083622363CD44F2C394`.
- The script audited both final files and reported `audited_files=2
  findings=0`. The sanitized QEMU then completed automatic calibration,
  launched KOV, ran an active battle at 60.124 logical/rendered FPS with zero
  audio underruns or overruns, and returned cleanly to a fully redrawn desktop.
- The instrumented measurement BDA was removed from the live NAND after the
  test. Transactional read-back confirmed that the installed file is the
  uninstrumented BDA with the hash above.

The repository-level `AGENTS.md` makes this gate permanent: every future
release or handoff must repeat the audit, and any finding remains a release
blocker.
