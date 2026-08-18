# Open-source project structure

Updated: 2026-08-18

The private research workspace contains vendor packages, raw NAND images,
toolchains, IDA state, game data, and generated test artifacts. Those files are
local inputs only. Public repositories contain reviewable source, documentation,
input hashes, and pinned component revisions.

## Published baseline

The two version repositories were created as public GitHub projects on
2026-08-18. Their current `main` commits and source-only archive tree identities
are:

| Project | Git commit | Files | Archived tree SHA-256 |
| --- | --- | ---: | --- |
| `bbk-h1-1x` | `451d165c40fd9ac1145b4733634450edfd141f39` | 106 | `64FDECD15041A30FCA9B4A164EE3ED17A6A46BE1E1F3C4543943CB7F942206DF` |
| `bbk-h1-2x` | `6266944ebe74100f932fd70fdfa627b0bb1f2669` | 110 | `B8C73DBE5E2F2811D301CC1DFC7020CAB7576240EA9DD903A1BBF1ECA7C8AECB` |

GitHub accepted both `main` branch updates after publication. Their exact
source ZIP archives and the parent research archive passed
`audit_release_secrets.py` with zero findings before publication. The 1.X
update contains only the shared bounded-FTL and batched-ECC tooling; native B
volume, Mission path and fixed-navigation work remains isolated to 2.X.

## Version repositories

| Repository | Local source | Purpose | Proprietary inputs |
| --- | --- | --- | --- |
| [`bbk-h1-1x`](https://github.com/MrDefinition1999/bbk-h1-1x) | `systems/1.X` | Reproduce the V1.41 NAND/emulator workflow and verified V1 BDA environment. | User supplies the two V1.41 recovery archives under `.local/inputs/`. |
| [`bbk-h1-2x`](https://github.com/MrDefinition1999/bbk-h1-2x) | `systems/2.X` | Reproduce V2.20 extraction/NAND work and continue the V1-game ABI compatibility layer. | User supplies the V2.20 PC and SD recovery packages under `.local/inputs/`. |

Both repositories include `inputs.lock.json`, `components.lock.json`, a source
boundary verifier, bilingual entry documentation, and a copy of the public
research tooling. Their `.local/` directories are ignored and may hold private
inputs and generated images without making those files publishable.

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
