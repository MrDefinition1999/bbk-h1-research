# Open-source project structure

Updated: 2026-08-18

The private research workspace contains vendor packages, raw NAND images,
toolchains, IDA state, game data, and generated test artifacts. Those files are
local inputs only. Public repositories contain reviewable source, documentation,
input hashes, and pinned component revisions.

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
