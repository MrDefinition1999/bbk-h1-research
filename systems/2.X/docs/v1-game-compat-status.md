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
replacement was tested and caused a black screen, so path translation stays
inside the Mission payload.

The storage layout is now dynamically verified. IDA analysis of the V2 OS
establishes separate NAND FTL windows: A uses physical blocks 120 through 1779,
and B uses blocks 1780 through 4095. The original retained V2 image has no B
records, so Resource Manager showing an empty B drive is the expected factory
state. A cannot be enlarged across block 1780 without colliding with the V2 B
scanner.

The guest-created B template uses native `Y100 V2.2` FAT16 geometry with
1,149,920 sectors. The complete `DataLib.dat` and `DataLibIndex.dat` are stored
under `B:\应用\数据\游戏\LYXZ`. Exactly five Mission-private
`A:\应用\数据\游戏\` prefixes are changed to B; the wrapper, V2 OS and every
other application keep their original A paths. B readback matches both trusted
V1 hashes.

On 2026-08-18 the fixed-input navigator launched the external compatibility
wrapper from a cold V2 BootROM boot. The user manually verified that the first
Mission entry enters the game and is playable. Two older menu experiments were
also classified: `V1Loop` reports missing Mission data, and the embedded
Mission experiment hangs. They were replaced with their native V2 applications
after the result was recorded, leaving only the verified external wrapper.

The navigator now clears restored UI state with two hardware Return events:
the first leaves the restored application for its remembered category page,
and the second returns to the subject desktop. A clean-image cold-boot
regression then reached Mission's character-information page with fixed input
only (`screenshots_used=false`, 71 input events). One terminal screenshot was
taken only after navigation completed; no screenshot matching controls the
route.

The cleaned local image is `work/v2-emulator/h1-v2-mission-b.raw`, 1,107,296,256
bytes, SHA-256
`529D02B39AD015B1B846C5F83B20ABF6F45B49590B771ED6C32E6994D46E512C`.
It remains private and is not a Git artifact.

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

Run longer Mission save/load, audio, touch and normal-exit regression sessions
against the cleaned image. Keep the successful external wrapper as the control;
do not reintroduce the missing-data or embedded-hang probes into the final menu.
Update the rule table, SDK tests, this status document and all affected public
repositories after each confirmed correction.
