# V1 games on V2: live research status

Updated: 2026-08-18

The filename is retained for link compatibility; this is now a continuously
maintained status document, not a handoff. Research remains active.

## Current conclusion

Running native V1 games on V2 is feasible through one application-level
SDK/ABI compatibility stage. The seven V1.41 games share the same BDA entry
address (`0x83C00020`), payload layout, and service-table ABI. They do not need
seven unrelated binary rewrites.

Static coverage across the seven games currently contains 120 used service
slots:

- 21 direct FS/MEM/SYS forwards;
- 88 GUI relocations; and
- 11 local compatibility shims for lifecycle, license/coin policy, RTC,
  legacy handles, and `RES+0x094`.

The source implementation is in
`h1-bda-sdk/examples/v2/v1_game_stage.c`. It preserves the 64-byte V2 prefix,
installs V1-shaped GUI/FS/SYS/RES tables, executes the unmodified V1 payload at
`0x83C00020`, and restores the V2 prefix after return.

## Important mappings

- `GUI+0x6E0` maps to V2 `GUI+0x9E4`; same-slot forwarding is invalid.
- `GUI+0x6A8` is a local game-mode gate/callback shim.
- `GUI+0x72C` maps to V2 `GUI+0x688`.
- `GUI+0x84C` is a state bridge to V2 `GUI+0x738`, not a plain relocation.
  V2 returns zero on its successful first lazy initialization; the bridge calls
  it again so V1 receives its expected nonzero initialized result.
- `GUI+0xAA4/+0xAA8` implement the explicit policy “allow without charging”
  because the V1 coin/reward system does not exist on V2.
- `RES+0x094` is a local return-zero shim.

The auditable rule metadata is in `scripts/h1_v2_game_compat_rules.py`; the SDK
contains a standalone copy plus regression tests. The published SDK component
commit is `352889b9fa9750cd8e4cb4806e5fc0e8edeac211`.

## Mission and storage state

The complete Mission BDA and its two DataLib files have been preserved and
byte-verified. Earlier blank Resource Explorer text and malformed dynamic
Chinese fonts were not file loss: the expanded image used V1 FAT geometry,
whereas V2 expects its native `Y100 V2.2` geometry. Global `A:` to `B:` kernel
replacement was tested and caused a black screen, so path translation must stay
inside a scoped filesystem shim.

The compatibility wrapper builds and passes static coverage/BDA validation, but
the complete Mission GUI loop has not yet passed final dynamic validation with
both DataLib files on a V2-native storage layout. This remains the next runtime
milestone; no success is claimed until the game screen persists and the trace
confirms the expected service path.

## Repository and runtime policy

- 1.X and 2.X are maintained separately under `systems/1.X` and `systems/2.X`
  and published as independent source repositories.
- Proprietary firmware, original game payloads, DataLib files, NAND images,
  runtime traces, and IDA databases stay local.
- Every verified milestone updates this document, Git, and the relevant GitHub
  repository before research continues.
- Obsolete artifacts go to the Windows Recycle Bin; QEMU/frontend processes are
  stopped after testing unless explicitly left for manual inspection.
- Every source archive and release is scanned with
  `scripts/audit_release_secrets.py` before publication.

## Next research milestone

Use a V2-native FAT layout with the complete Mission resource tree, run only one
8793 instance, launch the current state-bridge wrapper, and decode the trace at
the first failing service if Mission still returns to the desktop. Update the
rule table, SDK test, this status document, and all affected public repositories
after each confirmed correction.
