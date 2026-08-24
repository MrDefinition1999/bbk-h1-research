# V1 games on V2: live research status

Updated: 2026-08-24

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
commit is `067fe072477861dfc8949d7b1a55279fb92d2548`.

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

A later sparse visual check corrected the route. The real Mission icon is the
last icon on page two of Tools/Entertainment, not the first-page Time icon.
Page Up and Page Down cycle categories rather than pages. The fixed route now
selects Other at `(380,258)`/`(390,258)`, selects Tools/Entertainment at
`(430,258)`/`(440,258)`, taps its on-screen down arrow at `(455,216)` twice,
then selects Mission at `(402,61)` and sends hardware Confirm. Paired adjacent
category taps tolerate a dropped pen event and are idempotent.

The script now attaches to an already healthy cold boot by default; `--reset`
is explicit. It does not take or match screenshots. Instead it reads the
wrapper's reserved trace arena and requires a fresh `GAME_START` or
`GAME_RETURN` transition before reporting `mission-wrapper-confirmed`. A
2026-08-24 cold-boot run reached `GAME_START` with 28 fixed input events. One
redundant BootROM restart stopped in a repeated exception loop at PC
`0x81002834` while still displaying `请重新设置时间！`; EPC was
`0x8100305C` with Cause ExcCode 10 (reserved instruction), and the mapped
bytes at both virtual addresses were data rather than code. Backend input
counters continued to change while the guest instruction counter stopped near
6.6 million, proving this is not Return/Confirm key mapping. A later fixed reset
recovered normal instruction progress. `prepare_h1_v2_desktop.py` now rejects
non-progressing boots, retries at most three resets and verifies progress again
after desktop normalization.

The original diagnostic marker at virtual `0x83E00B00` overlapped unsafe
compatibility memory and could make Mission return early with no audio. It was
moved to the wrapper's reserved stage arena at virtual `0x83F0E000` (physical
`0x03F0E000`). The checked patcher requires exactly the two expected marker
instruction sequences and validates the resulting BDA. The deployed wrapper's
SHA-256 is
`154B601539E1B865A08D658B2C2038093C5BCA4E1C34935183977B5008E93C2C`.
The SDK source now writes a persistent trace header and generation counter in
the same arena; the navigator supports that format and the deployed compact
phase marker during migration.

The cleaned local image is `work/v2-emulator/h1-v2-mission-b.raw`, 1,107,296,256
bytes, SHA-256
`535D373C6DAEC12654C7611B81064AC2C64E1F742C9B4BFF0C6E67BC39A89C8F`.
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

Manually test 中国象棋, 俄罗斯, 宠物泡泡, 猫狗大战, 雷霆战机 and 黑白子 from the
final B-resource image. Record gameplay, audio, save/load and normal exit
separately for each title. Keep the successful external Mission wrapper as the
control; do not reintroduce the missing-data or embedded-hang probes. Do not
resume emulator-stutter work unless the user explicitly changes scope. Update
the rule table, tests, path document and relevant Git repositories after every
new verified result.

## Default-standing cadence regression

Cadence comparisons now use Mission's untouched default standing animation.
Operator and scripted map clicks are excluded because their timing and target
distance are not reproducible. Both 30-second samples used 64 MiB,
single-thread TCG and `instruction_clock=false`; the sampler only read runtime
status and did not inject input or capture screenshots.

| System | Changed frames/s | Median gap | P95 gap | Maximum gap | Guest minimum | Guest median | Audio DMA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V1 Mission | 1.735 | 578.472 ms | 619.822 ms | 633.773 ms | 6.780 M/s | 9.614 M/s | +323 |
| V2 compatibility stage | 1.739 | 589.222 ms | 624.195 ms | 707.183 ms | 8.505 M/s | 15.125 M/s | +323 |

V2 differs by only +0.23% in changed-frame rate and +4.373 ms at P95. It has
one 707.183 ms maximum outlier, but no approximately one-second instruction
collapse. At the reproducible default-standing position, the safe stage-arena
wrapper therefore matches V1 cadence closely and the former periodic stall is
not present. Earlier manually triggered movement samples are not used for this
conclusion. The sampler defaults to `--mode idle` so an omitted mode cannot
silently reintroduce the old method.

## Seven-game publishable source release

On 2026-08-24 the proven external compatibility stage was specialized for the
six remaining V1.41 games: 中国象棋, 俄罗斯, 宠物泡泡, 猫狗大战, 雷霆战机 and
黑白子. A compiler-free specializer changes only the verified external payload
path, compiled payload length and aligned cache-flush endpoint inside the
known-safe Mission wrapper. Each expected instruction sequence must occur
exactly once, and the unsafe pre-stage-arena template hash is rejected.

The six sources use 106 unique services, all covered by the shared V1-on-V2
rules (`unmapped=0`). The final installer stores six launcher BDAs and six
executable payloads on hidden A, but stores all sixteen packaged game resources
under `B:\应用\数据\游戏`. It changes only verified one-byte A-to-B drive
letters inside the payloads, with exact expected counts per game. 宠物泡泡's
runtime save path `B:\应用\数据\游戏\user.bin` is redirected as well.

A and B are written and verified independently in fixed windows
`[0x40,0x6F4)` and `[0x6F4,0x1000)`. The A phase proves B unchanged; the B
phase proves the entire boot/A byte range unchanged. Every installed file is
reopened through FAT and byte-compared. The existing playable Mission and its
B-resident DataLib files are preserved.

The final private verification image is
`work/v2-emulator/h1-v2-v1-games-b.raw`, 1,107,296,256 bytes, SHA-256
`7CDBA2CA81CB3E252752C39F70642FBA8648AB8CBC3F2409B241BF3C1EA0D031`.
Its A and B region hashes are
`E37A4C6EAF5A80056C113D6612F003F7918AE8063FE0793A3F8606569BA0E108`
and
`E7C1275FD4BFAF705C2539BFB0606C755474A7B77D5BA0CA43F4E3652AF0A56A`.
A gained two mapped logical units and retains 4,737 free clusters; B gained
167 and retains 23,602. Full guest paths and checked payload offsets are in
`docs/20-v2-game-release.md`.

The publishable package contains source, tools, tests and documentation only.
It excludes firmware, NAND, original BDA/game/AVI content, generated binaries
and IDA files. Mission is user-verified playable. The other six have static ABI
and byte-level install verification but still require manual gameplay, audio,
save and normal-exit testing; no unverified runtime claim is made.

## Flying Video emulator finding

The stock V1.41 `飞天影音` directory contains exactly two AVI files. The
reproducible installer copied them to `B:\飞天影音`, the volume visible to V2
Resource Manager. Fixed navigation opens Flying Video's first lower menu
button, waits for recursive B search, ticks the first result's checkbox and
uses the inner Open point; row highlighting alone does not select a file.

The user verified both recurring playback pauses and a guest freeze after an
AVI reaches its natural end. The same intermittent symptom had been observed
during Mission movement, so it is classified as an emulator/runtime fault, not
a game-port fault. A native ARM64 QEMU build did not fix it. At the last AVI
frame, diagnostics showed FIFO depth 30 and DMA complete/rearm 1233/1232. An
isolated older AIC boundary-drain build generated 894 underruns in about 17
seconds and later stalled, so it was rejected and all maintained sources were
restored to the stable baseline.

The user explicitly stopped emulator-stutter work. AVI artifacts are not part
of the game release, and the obsolete combined AVI/test image must not be used
as a release base. Continue any AIC/cadence investigation separately.
