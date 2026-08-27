# Open-source project structure

Updated: 2026-08-27

The private research workspace contains vendor packages, raw NAND images,
toolchains, IDA state, game data, and generated test artifacts. Those files are
local inputs only. Public repositories contain reviewable source, documentation,
input hashes, and pinned component revisions.

## Published baseline

The two version repositories were created as public GitHub projects on
2026-08-18. Their current `main` commits and source-only tree identities are:

| Project | Git commit | Files | Archived tree SHA-256 |
| --- | --- | ---: | --- |
| `bbk-h1-1x` | `b68785b1ff4e19495527d5379aaeecaf7fa96e25` | 106 | `A273AE90FE030FE3B0E8E5BF51FE6ACA5AB3FE8B3264DA296ED9D0E36F2E8B35` |
| `bbk-h1-2x` | `71daedd434ab47fd885a3c7e655fe2a471a76c69` | 114 | `B1724C974C0564878322A985D11BD03B06974B77DDA28B126C6A568EED5DBA78` |

GitHub accepted both `main` branch updates. Before the 2026-08-24 push, their
exact source ZIP archives passed `audit_release_secrets.py` with zero findings.
The 1.X ZIP SHA-256 is
`5B5580A8E7FB6E71DD408BED075D011E347486F4BED1473E48D9B6CE446ADA7B`;
the 2.X ZIP SHA-256 is
`E7F67A53659B1E345FF757B9B00D6D4F0B72B0B013F8C4DDC55F75C417F6CA9E`.
The 1.X change only advances the shared SDK pin. Safe Mission trace placement,
signature-verified page-two navigation and default-standing cadence tooling
remain isolated to 2.X.

## Version repositories

| Repository | Local source | Purpose | Proprietary inputs |
| --- | --- | --- | --- |
| [`bbk-h1-1x`](https://github.com/MrDefinition1999/bbk-h1-1x) | `systems/1.X` | Reproduce the V1.41 NAND/emulator workflow and verified V1 BDA environment. | User supplies the two V1.41 recovery archives under `.local/inputs/`. |
| [`bbk-h1-2x`](https://github.com/MrDefinition1999/bbk-h1-2x) | `systems/2.X` | Reproduce V2.20 extraction/NAND work and continue the V1-game ABI compatibility layer. | User supplies the V2.20 PC and SD recovery packages under `.local/inputs/`. |

Both repositories include `inputs.lock.json`, `components.lock.json`, a source
boundary verifier, bilingual entry documentation, and a copy of the public
research tooling. Their `.local/` directories are ignored and may hold private
inputs and generated images without making those files publishable.

## H2 V2.2L project

H2 is currently maintained as `systems/H2-2.X` inside
[`bbk-h1-research`](https://github.com/MrDefinition1999/bbk-h1-research), rather
than as a third standalone version repository. Commit `eab496d` introduced the
reproducible H2 V2.2L image builder, verifier, ARM64 runtime, pinned OpenNoah
QEMU/BootROM components and H2-specific Mission stage. The user-owned 2 GiB
eMMC, vendor recovery package, QEMU binaries, commercial Mission/S1 data,
debug traces and sector journals remain ignored local inputs.

The H2 base system is dynamically verified, but neither Mission branch is a
finished release: the H1 V1 payload reaches menu/story and fails a 32 MiB scene
allocation, while the current original-S1 payload reaches game code without
obtaining a visible H2 foreground window. The exact current boundary is
recorded in `22-current-project-handoff.md`; do not publish either branch as a
playable H2 port.

## Shared public components

| Repository | Role | License boundary |
| --- | --- | --- |
| [`bbk-h1-bda-sdk`](https://github.com/MrDefinition1999/bbk-h1-bda-sdk) | Freestanding MIPS BDA builder, verified H1 APIs, probes, and the V1-on-V2 compatibility stage. | Original SDK source and documentation: Apache-2.0. |
| [`bbk-h1-emulator`](https://github.com/MrDefinition1999/bbk-h1-emulator) | H1/JZ4740 QEMU machine, Web frontend, input, audio, BootROM path, and reproducible Windows build. | GPL-2.0 and the inherited QEMU/upstream terms. |
| [`bbk-h1-research`](https://github.com/MrDefinition1999/bbk-h1-research) | Cross-version findings and the scripts from which the two version projects are materialized. | Original source and documentation: Apache-2.0. |

The version repositories fetch the SDK and emulator at full 40-character commit
IDs. This avoids duplicating their histories while keeping every reproduction
anchored to reviewed source.

## Excluded material

- Vendor RAR, EXE, UPD, firmware, BootROM, U-Boot, OS, ExtOs, and raw NAND.
- Commercial BDA/DLX, ROM, BIOS, PAK, WAD, audio, video, and game data.
- IDA databases, debugger state, runtime logs, screenshots not selected as
  documentation evidence, compiler caches, toolchains, and QEMU build trees.
- User names, host names, user-profile paths, workspace paths, credentials, and
  tokens.
- KOV port source while its upstream provenance/license remains unresolved.

## Continuous publication rule

Every verified result must update the applicable local status document and Git
history. Before a push, build a source archive from tracked files and run
`python scripts/audit_release_secrets.py` against the archive itself. Generated
or obsolete local artifacts are removed through the Windows Recycle Bin only;
test QEMU/frontend processes are stopped when no longer needed.
