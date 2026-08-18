# Knights of Valour Plus H1 port

This document records the H1 port investigation for `kovplus`, the PGM V119
release commonly known in Chinese as `三国战纪：风云再起`. Confirmed facts are
kept separate from implementation work and real-device acceptance.

## ROM ownership and release boundary

**Confirmed (2026-07-31):**

- The user supplied seven cartridge dumps under the private top-level `kov`
  directory. They remain input data and must never be copied into a public
  source archive, BDA, or redistributable install package.
- `kovplus.zip` is the split V119 clone. It contains only `p0600.119`
  (4,194,304 bytes, CRC32 `e4b0875d`) and requires the shared game data from
  `kov.zip`.
- The target driver requires the following game ROMs: `p0600.119`,
  `t0600.rom`, `a0600.rom` through `a0603.rom`, `b0600.rom`, `b0601.rom`, and
  `m0600.rom`. Their combined uncompressed size is 56 MiB.
- The supplied directory does not contain the PGM motherboard BIOS archive.
  The reviewed driver expects `pgm_p01s.rom` (CRC32 `e42b166e`),
  `pgm_t01s.rom` (CRC32 `1a7123a0`), and `pgm_m01s.rom` (CRC32 `45ae7159`).
  Copyrighted BIOS data will not be downloaded or redistributed. A clean-room
  boot path or a BIOS dump supplied by its owner is required.

The private input archive SHA-1 values are recorded only for local
reproducibility:

| Archive | SHA-1 |
| --- | --- |
| `kov.zip` | `EDB2045173A4175F1080E4DB552FC6C4E23B4CBC` |
| `kov115.zip` | `43654DC0A78D4A2B468575FFA44B0E2D36A53C79` |
| `kov2.zip` | `561D50E8401E1A61865417C76624C9A08E75AEAC` |
| `kovj.zip` | `BCFBD2D8A8405C64F94F30F603FE1C4DCF572E88` |
| `kovplus.zip` | `B49835D085A56ACC63C29B60EE9402DB0CD21593` |
| `kovplusa.zip` | `9809F158D0B5DEDC45365DB7129C6F2C0E3901B4` |
| `kovsh.zip` | `2600B4D95AC0C4AF25D7BB635E38A896B2D7DA94` |

## Verified open-source baseline

**Confirmed (2026-07-31):**

- The closest hardware baseline is the archived GitHub repository
  `dmitrysmagin/fba-a320`, fixed locally at commit
  `68af7cc0065757c688595adc409f5d47977793ae`.
- It is FBA 0.2.96.86 for Dingoo A320/A380 and OpenDingux. Its `kovplus`
  driver identifies V119, the exact program CRC above, and marks the game
  working.
- The driver uses a Motorola 68000 main CPU, Z80 sound CPU, ICS2115 wavetable
  sound, PGM tile/sprite video, and emulated ASIC3 protection. This KOV target
  does not use the ARM7 protection CPU found in later PGM games.
- The Dingoo build already contains a MIPS32R1 A68K assembly core and a CZ80
  core. Those are the preferred H1 CPU engines; using a portable interpreter
  would discard a large part of the available JZ4740 performance.
- The repository has no root license manifest and GitHub reports no repository
  license. Individual SDL frontend files are GPL-2.0-or-later, while some
  imported CPU/font components carry non-commercial or personal-use terms.
  Any source handoff must preserve per-file notices and must not be represented
  as a uniformly permissive package.

## Display and input target

**Confirmed from the driver and H1 runtime:**

- PGM output is 448x224 at 4:3. It fits the H1 480x272 panel without scaling.
  The H1 port will center RGB565 output at `(16, 24)` and leave black borders.
- The renderer is software-driven. JZ4740 IPU and LCD DMA do not accelerate
  PGM tile/sprite composition; the useful hardware path is one final aligned
  RGB565 submission after rendering.
- H1 keyboard controls will expose movement, four attack buttons, coin, start,
  pause/menu, save/load state, and a reliable held-key exit. Final key choices
  remain open until the first interactive emulator build.

## Memory feasibility

**Confirmed from the A320 source:** the unmodified PGM allocator cannot run in
the H1 memory budget. For V119 it allocates approximately:

| Region | Approximate size |
| --- | ---: |
| 68000 program, BIOS, working RAM and protection space | 6.5 MiB |
| packed tile ROM including BIOS prefix | 12 MiB |
| fully expanded 5bpp tile data | 19.2 MiB |
| sprite colour ROM | 28 MiB |
| sprite mask ROM | 12 MiB |
| sound ROM including BIOS prefix | 8 MiB |
| **Total before frontend/frame/audio overhead** | **about 85.7 MiB** |

The A320 README explicitly recommends swap. H1 has 64 MiB physical RAM and
must also retain the BBK OS, BDA image, task stacks, framebuffer and audio
buffers, so copying the A320 allocation strategy would be unsafe.

**Confirmed port decision:** build a game-specific core rather than the full
FBA frontend. Remove the 19.2 MiB permanent tile expansion, decode tiles on
demand into a bounded cache, and page cold sprite/sample data from an external
user-generated data pack. The pack format must be independently reproducible
from the user's `kov.zip` and `kovplus.zip`, support per-page CRC validation,
and contain no machine-specific path.

**Confirmed pack implementation (2026-07-31):**

- `prepare_rom_pack.py` validates all nine exact filenames, lengths and CRC32
  values before writing anything permanent.
- The format aligns ROM regions to 64 KiB, records a CRC32 for each of the 896
  pages, hashes the complete manifest, and is byte-for-byte deterministic.
- Three host regressions cover deterministic round-trip, corrupted-page
  rejection, and wrong-input rejection with transactional cleanup. A fourth
  regression compiles and executes the C LRU reader, including cross-page
  reads, direct page-to-slot hits, forced eviction, and stale-directory
  rejection with two cache slots.
- The actual private pack is 58,785,792 bytes with SHA-256
  `6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53`.
  A full page verification passed. The file remains below `work/private` and
  is excluded from every release/handoff archive.
- The freestanding cache reader cross-compiles cleanly for MIPS32R1 with all
  warnings treated as errors. Its current object contains 2,252 bytes of text
  and no data or BSS; cache storage is supplied by the H1 runtime instead of
  inflating the BDA image.

## Performance plan

The first accepted build will use the proven MIPS32R1 A68K core, CZ80, direct
448x224 RGB565 rendering, 32-byte-aligned cache pages, 22.05 kHz output, and
fixed-size arenas. Measurements will separate 68000, Z80/ICS2115, tile,
sprite, storage-cache, and presentation time. JZ4740 MXU, DMA, cache-control,
or overclock changes will not be enabled without emulator safety and real H1
ownership/coherency evidence.

## Clean-room low-memory boot

**Confirmed and implemented (2026-07-31):**

- The V119 cartridge supplies initial SSP `0x00820000` and reset PC
  `0x00100282`; its reset routine performs cartridge-side hardware setup.
- The game compares low memory at `0x230` with `V0000`. A match bypasses the
  legacy call through `0x248`.
- Static call-site analysis shows `0x23c/0x240` are an optional query/command
  pair. Calls through `0x244` occur inside bounded input waits and therefore
  require an immediate-return service, not a null pointer.
- `kov_bootstrap.c` builds a new 128 KiB low-memory page from zero, copies the
  complete `0x80`-byte V119 cartridge vector table at runtime, writes `V0000`,
  and installs local minimal stubs at all five pointer slots from `0x238`
  through `0x248`. The copied table comes from the CRC-verified private pack;
  neither the public source nor the BDA contains cartridge or PGM BIOS bytes.
- IDA confirmed that V119 supplies IRQ3/IRQ4/IRQ6 handlers at
  `0x00100972/0x00100982/0x00100992`. IRQ6 saves all 68000 registers, calls the
  frame handler at `0x00103ae2`, restores the registers and executes `RTE`.
  Keeping the earlier local RTE at vector `0x78` skipped that handler and left
  the frame flag at `0x806130` clear forever.
- Host tests validate the complete vector range, every service target, byte
  order, and a clean MIPS32R1 cross-compile. The real V119 IRQ6 vector is now
  accepted under the final A68K core.

## V119 program decryption

**Confirmed and implemented (2026-08-01):**

- `kov_decrypt.c` implements the exact `pgm_kov_decrypt` address masks and
  256-byte table from the reviewed FBA A320 source while preserving explicit
  provenance. The implementation contains no game or motherboard ROM data.
- It reads and writes the FBA/A68K word-swapped representation explicitly, so
  results do not depend on the compiler host's byte order or unaligned
  `uint16_t` access. A range interface accepts the absolute ROM word index,
  allowing deterministic whole-image or page-sized operation.
- A public 512-byte synthetic vector passes. The private regression decrypts
  the exact V119 `p0600.119` image and matches the earlier FBA-generated 4 MiB
  result byte for byte. The same source cross-compiles for MIPS32R1 with all
  warnings treated as errors.

## Early boot and interrupt probe

**Confirmed (2026-08-01):**

- The diagnostic Musashi execution starts at cartridge PC `0x00100282` with
  SSP `0x00820000`, completes the ASIC28 initialization, uploads the initial
  Z80 image through `0xc10000..0xc1ffff`, enables the sound CPU with `0x5050`,
  and reaches the cartridge wait loop at `0x00103a9c`.
- The earlier repeated `pc=0x00000120` report was a probe-observation error,
  not a CPU lock. The probe executed a complete CPU slice, injected IRQ6, and
  then printed the PC before the local RTE handler had its next slice.
- The corrected probe records the pre-interrupt PC, acknowledge count, RTE
  count, vector contents and exception stack independently. IRQ6 resolves to
  `0x00000120`, fetches opcode `0x4e73`, stacks SR `0x2004` and return PC
  `0x00103a9c`, then restores that PC on the next slice. Both pulse and held-
  until-observed modes produce the same valid return sequence.
- The local-RTE result above was retained as an isolation test, not the final
  boot contract. The final bootstrap copies V119 vector `0x78`, which resolves
  to cartridge wrapper `0x00100992` and executes the full per-frame chain.

## JZ4740 A68K integration

**Confirmed on the ARM64-host H1 emulator (2026-08-01):**

- The final main-CPU engine is generated from the reviewed fba-a320
  MIPS32R1 A68K source, whose SHA-256 is locked to
  `F15040E0E32DA40F87222E74E158463F0661E2DC5FBA1A4ED58E341E7C9592E9`.
  The build invokes the generator with local basenames, so its jump-table
  include contains no workspace path.
- The generated core contributes 604,600 bytes before final section garbage
  collection. The complete executable probe BDA is 651,188 bytes and fits the
  retained 983,040-byte application chain without allocating NAND clusters.
- The reusable `kov_machine` map runs cartridge code from a contiguous 5 MiB
  word-swapped fetch image and provides mirrored 68000 RAM, BG/text/row RAM,
  palette/video registers, ASIC28, ASIC3, calendar, inputs, sound latches and
  the shared Z80 window.
- The H1 probe reached the V119 wait loop near `0x00103a9c`, uploaded more than
  32 nonzero bytes to Z80 RAM, enabled the Z80 through the `0x5050` protocol,
  acknowledged IRQ6, executed V119's frame wrapper at `0x00100992`, and
  returned from the cartridge handler to the interrupted code.
- This A68K generator retains an `RTECallback` field for structure
  compatibility but its generated `RTE` path does not invoke that callback.
  The acceptance check therefore observes IRQ acknowledgement followed by the
  actual returned PC; a callback counter would be a false failure.

## Sound bus and ICS2115

**Implemented and host-tested (2026-08-01):**

- `kov_sound_bus.c` implements the PGM latch mapping, Z80 reset/enable value
  `0x5050`, latch-zero NMI, Z80 port groups `0x80/0x81/0x82/0x84`, and the
  exact byte/word view of the shared 64 KiB Z80 RAM.
- `kov_ics2115.c` implements the KOV-used 32-voice register set, timers,
  pending IRQ and voice completion behavior. Samples are obtained through a
  callback, allowing the 4 MiB `m0600.rom` region to remain in the bounded
  `KOVH1.PAK` cache rather than consuming permanent H1 RAM.
- H1 output is generated directly at 22,050 Hz. Since the chip model advances
  at 33,075 Hz, its `fc << 2` address delta becomes exactly `fc * 6`; no
  general resampler or fractional state is needed.
- A synthetic end-to-end regression programs a voice through the port
  interface, renders stereo PCM, acknowledges voice and timer IRQs, verifies
  sound latches/NMI and shared-RAM byte order, and cross-compiles both modules
  for MIPS32R1 with warnings treated as errors.
- A 600-frame ARM64-host H1 emulator probe passed real V119 execution through
  A68K, CZ80 and IRQ6, then observed ICS2115 port programming, an active voice,
  paged reads from private `m0600.rom`, zero page faults and nonzero PCM. The
  earlier 240-frame failure was a too-short four-second startup window, not an
  ICS2115 defect.
- V119 uses the `sangoDIP` default `0x05` (World). Machine reset now exposes
  guest DIP word `0xfffa` instead of the incorrect all-high `0xffff` value.

## CZ80 integration

**Confirmed on the ARM64-host H1 emulator (2026-08-01):**

- Every reviewed CZ80 source/include file is hash-checked before the build.
  The core remains under its original non-commercial attribution terms.
- The 263,424-byte flag-table workspace is rebuilt by `Cz80_InitFlags()` and
  is placed in the H1 `NOLOAD` area. It consumes runtime RAM but no BDA/NAND
  bytes. CZ80 adds about 37 KiB to the executable probe, producing a
  688,372-byte BDA.
- The original A320 core stored `BasePC` in a signed `int` and treated values
  at or below zero as unmapped. H1 heap pointers use the `0x82xxxxxx` range, so
  valid pointers appeared negative and caused a null fetch on the first Z80
  instruction. The reproducible H1 transform uses an unsigned 32-bit base and
  treats only zero as unmapped.
- With that H1 address-space correction, the uploaded sound program executed
  at 8.468 MHz using the original two-way frame interleave. The diagnostic
  required nonzero executed cycles and a nonzero Z80 PC while retaining the
  A68K wait-loop and IRQ6/RTE checks; all passed.

## Current status

- Source/ROM driver match: **confirmed**.
- Legal ROM separation: **confirmed**.
- 64 MiB feasibility of unmodified FBA A320: **rejected**.
- Game-specific loader and cache format: **implemented and integrated into the
  native H1 runtime**.
- Clean-room BIOS-free boot page: **accepted under the JZ4740 A68K core on the
  ARM64-host emulator**.
- V119 program decryption: **implemented; exact private-ROM and MIPS32R1
  regressions passed**.
- Clean-room early execution and IRQ6/RTE return: **confirmed under both the
  diagnostic Musashi core and final MIPS32R1 A68K core**.
- PGM sound bus, CZ80 scheduling, ICS2115 synthesis and H1 audio descriptor
  submission: **implemented and accepted on the ARM64-host emulator with zero
  sample faults and zero DMA underruns in the five-minute stress run**.
- H1 loader diagnostic: **accepted on the ARM64-host emulator (2026-08-01)**.
  The final `其它` slot opened the private read-only host pack, verified the
  manifest and all 896 page CRCs, matched the complete V119 program CRC,
  decrypted it, and displayed PASS for the clean-room vectors/RTE checks.
  The fixed desktop workflow launches this slot on the selection touch itself;
  sending a later permanent Confirm dismisses the diagnostic dialog and must
  not be interpreted as a launch failure.
- JZ4740 A68K integration: **accepted on the ARM64-host emulator
  (2026-08-01)**; deterministic generation, full MIPS link, early boot, Z80
  upload, V119 IRQ6 handling and paged ICS2115 PCM all passed.
- H1 gameplay runtime, icon and sound: **accepted on the ARM64-host emulator**.
  Physical-H1 acceptance remains pending owner testing.

## Bounded PGM renderer

**Implemented and host-tested (2026-08-01):**

- `kov_renderer.c` composes the native 448x224 PGM image in the confirmed
  order: priority-one sprites, background, priority-zero sprites, then text.
  It accepts a configurable output stride, so the H1 runtime can render
  directly into the centered `(16,24)` window of one 480x272 RGB565 buffer
  without scaling or a second full-frame copy.
- The 5bpp background format is decoded from 640 packed bytes to one 32x32
  tile only on a bounded cache miss. Text tiles use a separate 256-entry
  expanded cache. Sprite mask and colour streams keep contiguous page windows
  and request a new validated pack page only at a boundary.
- Tile addresses retain FBA's virtual 4 MiB motherboard prefix. Reads below
  that prefix are rendered as transparent because this clean-room port does
  not contain the copyrighted PGM tile BIOS.
- The real palette map is 0x900 RGB555 entries: sprites `0x000..0x3ff`,
  background `0x400..0x7ff`, and text `0x800..0x8ff`. The reviewed old A320
  renderer used a `0x1f0` text-palette mask that could address beyond this
  hardware range; the H1 renderer uses the bounded 16-bank `0x0f0` mask.
- A ROM-free synthetic regression verifies exact layer priority at selected
  pixels, virtual tile offsets, RGB555-to-RGB565 conversion, cache hits and
  preservation of pixels outside the 448-wide viewport. The source also
  cross-compiles for MIPS32R1 with `-Wall -Wextra -Werror`.
- The current sprite path deliberately matches the proven A320 baseline's
  unscaled semantics. Sprite zoom, row scroll and any MXU specialization are
  deferred until gameplay capture and timing counters establish a concrete
  correctness or performance need.

## Native gameplay runtime and performance

**Implemented and emulator-accepted (2026-08-01):**

- `h1_kov_runtime.c` runs V119 directly with the generated MIPS32R1 A68K core,
  CZ80, ICS2115 and the bounded renderer. It is a native H1 BDA, not an FBA
  frontend and not a nested virtual machine.
- The 448x224 image is centered unscaled in a 480x272 RGB565 screen. Movement
  uses arrows or WASD; `J/K/U/I` are the four arcade buttons; Enter/Confirm is
  Start, Space is Coin, `P` pauses, and holding Back/Escape exits. Exit uses a
  750 ms hardware-timer threshold instead of a frame count, so a slow frame
  rate cannot make the real-device hold duration unpredictable.
- The 64-page pack cache now maintains a page-to-slot directory. Hot hits are
  O(1), while eviction retains full LRU behavior and invalidates the old
  directory entry transactionally. ICS2115 single-byte sample reads use the
  fixed 64 KiB page geometry directly.
- Background rendering examines only cells whose exact scrolled coordinates
  intersect the viewport: 98 cells at zero scroll instead of all 4096. Text
  similarly examines 1568 instead of 2048 cells at zero scroll. A ROM-free
  regression locks these bounds as well as the pixels and layer order.
- Expanded background and text caches retain global LRU replacement but add
  direct tile-to-slot directories. This costs about 430 KiB of heap and avoids
  both the old 128/256-entry hit scans and the collision losses measured with
  an attempted four-way cache.
- RGB555 palette entries are converted only when their source word changes.
  The final port is built with `-O3 -fomit-frame-pointer`; generated A68K
  remains the reviewed MIPS32R1 assembly implementation.
- In one controlled ARM64-host browser-foreground battle path, the rejected
  four-way-cache build produced 186 frames in 10.3 seconds (18.1 FPS), the
  full-LRU directory build produced 236 (22.9 FPS), and the final palette/O3
  build produced 278 in 10.2 seconds (27.3 FPS). These are comparative QEMU
  presentation measurements, not a physical-H1 frame-rate claim.
- The final build completed a 300-second automated run with the same QEMU PID,
  293 periodic movement/attack/skill actions, frame sequence 12901 to 18961,
  and zero audio underruns or overruns. Live checks also accepted Coin, Start,
  character selection, movement, all four action buttons, scene transitions,
  and clean desktop repaint after held-key exit.
- MXU, IPU, speculative cache-control writes, DMA ownership changes and
  overclocking remain disabled. No verified hotspot currently justifies the
  coherency and real-hardware risk; the port already uses JZ4740-compatible
  MIPS32R1 A68K assembly and aligned RGB565 submission.

### Emulator frame-pacing investigation

**Confirmed on the ARM64-host emulator (2026-08-01):**

- The fixed logical-frame interval measured 21.925 FPS at baseline. Native
  68000/Z80 cycle budgets match the A320 port, but 15.04 seconds of host time
  advanced the H1 application timer by only 9.60 seconds and exposed an
  effective 80 Hz tick rate of about 40.6 Hz. The slow motion is therefore a
  virtual timer scheduling problem, not an intentional reduction in emulated
  arcade CPU cycles.
- Removing the guest wait reached 116.406 logical FPS but made logic and audio
  run too fast. Fixed render skipping reached 38.116 logical FPS while drawing
  19.026 FPS. A 448x224 partial display submission and verified 68000 IRQ-idle
  detection did not improve the baseline. These variants are rejected.
- A first cooperative bridge that only released the vCPU thread with
  `g_usleep` regressed to 12.109 logical FPS. Over roughly 1,200 frames it made
  19,058 calls and requested 112,214 ms of host sleep because the guest reread
  the same slow software timer after every sleep. Audio still reported zero
  underruns and overruns, but this pacing design is rejected.
- The accepted emulator-only pacing path pairs one bounded cooperative wait
  per frame with a read-only host monotonic-millisecond register. A fixed
  600-frame comparison measured 60.164 logical FPS and 60.064 rendered FPS,
  versus 21.925 FPS at baseline: 2.74 times the original rate, or a 174.1%
  increase. The one-call design replaced about 16 repeated sleeps per frame.
- The final 18,000-frame acceptance interval completed 18,003 logical and
  rendered frames in 300.013 seconds (60.007 FPS). The QEMU PID remained
  unchanged, audio reported zero underruns and overruns, memory remained
  stable, and a 0.85-second held Back action returned cleanly to the desktop.
  During the extended run the bridge count stayed approximately one per frame
  and QEMU averaged about 53-56% of one host CPU core.
- A post-strip release regression repeated the measurement in an active battle,
  rather than a title or static boot scene. It completed 3,614 logical and
  rendered frames in 60.109 seconds (60.124 FPS), with 59.742 cooperative
  bridge calls per second, a stable QEMU PID, zero audio underruns/overruns and
  55.5% average use of one host CPU core. The lower browser frame-packet count
  observed in an earlier sample was therefore transport sampling, not guest
  slow motion.
- After that diagnostic, the uninstrumented 703,668-byte emulator BDA was
  restored transactionally and read back byte-for-byte. Its 0.85-second held
  Back path exited cleanly and the H1 desktop background, icons and dock all
  redrew correctly under the finalized ARM64 executable.
- Host pacing is compiled only into the private emulator BDA. Real-H1 builds
  continue to use the firmware timer; no MXU, IPU, DMA, cache-control or clock
  change is enabled without physical-device evidence.

## ROM-free real-device release

### Physical-audio queue correction

**Confirmed on the ARM64-host H1 emulator (2026-08-01):**

- Factory Mission initializes the H1 output service with `mode=1`. The KOV
  port had used an unverified `mode=2`; DMA still advanced in QEMU, but the
  submitted stream was all zero. KOV now keeps the ICS2115 stereo synthesis
  internally and performs an equal left/right downmix before submitting the
  confirmed 16-bit mono H1 format.
- PCM storage and 32-byte descriptors are allocated independently. Both live
  pointers are aligned to 32 bytes while the original allocator pointers are
  retained for teardown.
- Submitting one 367/368-sample descriptor per emulated frame kept all 16
  firmware queue nodes continuously active. The firmware activity state could
  eventually roll to zero and permanently replace later buffers with silence.
  The runtime now accumulates exactly 1,000 mono samples per submission and
  uses a 1,008-sample aligned slot stride.
- A 45.013-second title-to-battle capture after the change had peak 15,934,
  RMS 3,089.967 and a 0.651013 non-silent sample ratio. The diagnostic build
  completed 3,247 submissions with zero submission failures, DMA underruns or
  overruns while the image continued to advance. The release build omits all
  diagnostic counters.

Physical-H1 audible-output confirmation remains required; emulator DMA
counters alone are not treated as proof of real-device audio.

The real-device BDA and its public archive are built reproducibly with:

```powershell
python scripts/build_kov_h1_release.py
```

The release stages only `H1KOVPlus.bda`, the deterministic pack-generation
tool, installation/control instructions, and checksums. The build script
rejects ROM, PAK, ELF, image, log, JSON deployment and Python-cache artifacts,
then runs the icon and privacy audits against the stage and final ZIP. The
private `KOVH1.PAK` remains under `work/private/kov` and is never copied.

The real-device layout is `A:\应用\程序\H1KOVPlus.bda` plus the owner-generated
`A:\应用\数据\KOVH1\KOVH1.PAK`. The app appears as `三国战纪+` in the H1 game menu. This
release is accepted on the ARM64-host H1 emulator; physical-H1 acceptance is
pending owner testing.

The combined package with the earlier 18 H1 ports is built with:

```powershell
python scripts/build_all_h1_release.py
```

It produces a combined archive with every BDA in `A-root/应用/程序`. All APP,
WAD, PAK and C15PAK resources are below `A-root/应用/数据`; the 18 A320/DOOM
BDA files are rebuilt with matching CP936/GBK paths rather than merely moving
their data. After the ROM owner explicitly authorized sharing, the verified
`KOVH1.PAK` is staged at `A-root/应用/数据/KOVH1/KOVH1.PAK`, so copying
`A-root` is sufficient to run KOV.

**Combined build (2026-08-01):**

- `H1-all-games-real-hardware-2026-08-01.zip`: 123,631,885 bytes, SHA-256
  `AF57976BFD840433C49F10526CF0513875A5AE9B93F2E7C6F277D077AD8A1A20`.
- ZIP layout: 41 files total. Its only top-level entries are `A-root` and
  `游戏说明.txt`; `A-root` contains the 20 BDA files, 18 existing runtime data
  files, the authorized KOV pack, and the emulator-accepted CS15 pack. Every
  one of those 20 resource files is below `A-root/应用/数据`.
- All 20 BDA icon sets and all 20 embedded GBK resource paths passed
  validation. The stage and archive privacy audits reported zero findings; no
  ELF, build tool, checksum manifest, source archive, debug report, screenshot,
  log or Python bytecode file is present.

**Audio-corrected combined build (2026-08-02):**

- The owner's first combined-package test found normal physical sound only in
  DOOM, Doudizhu and Zhao Yun. Every other title in that archive was therefore
  treated as unaccepted rather than inheriting earlier emulator status.
- The 16 shared A320-runtime BDA files were rebuilt with 16-bit mono H1 output,
  U8/S16 and mono/stereo source conversion, 1,000-sample submissions and
  32-byte-aligned 1,008-sample slots. Puzzle Bobble, one of the titles reported
  silent, produced nonzero decoded PCM through this exact replacement bridge.
- The independent 7 Days bridge uses the same queue geometry and produced
  nonzero 16 kHz title music with zero DMA underrun. CS Lite's independent
  bridge produced nonzero 22.05 kHz gun audio with zero underrun. KOV produced
  nonzero title-to-battle PCM for 45 seconds with zero submission failure,
  underrun or overrun. DOOM retains its already accepted physical audio path.
- `H1-all-games-real-hardware-2026-08-02.zip` is 123,636,624 bytes, SHA-256
  `B78E29FDA73354A34C47AE2C906A026F4A6CC20611D007AADF3A07F1AF3846CE`.
  It has 41 files: 20 BDA files, 19 game-data files and packs, and one UTF-8
  operation guide. Its only top-level entries are `A-root` and
  `游戏说明.txt`; every game resource is under `A-root/应用/数据`.
- The 71-test H1 SDK suite and 20-test CS suite pass. All 20 icon sets and all
  embedded resource paths pass release audit. The stage, ZIP content and ZIP
  container privacy scans report zero findings. Physical audio acceptance for
  the replacement builds remains pending the owner's real-H1 retest.

**Physical-H1 rejection (2026-08-02):**

- The owner measured no KOV frame-rate improvement over the 2026-08-01 build.
  The earlier 60 FPS and 2.74x measurements came from the emulator-only host
  monotonic clock/cooperative-yield path. They are not evidence of faster code
  on JZ4740 hardware.
- The hardware KOV build does not enable the emulator bridge, host clock,
  fixed frame skip, MXU, IPU, DMA takeover, cache-control changes, overclocking
  or a modified CPU clock. Therefore no physical-H1 performance improvement is
  currently established.
- The same combined archive made PAL, Zhao Yun and Doudizhu corrupt the display
  and lock up. Its shared A320 physical-audio bridge is rejected and separated
  from the emulator implementation. The full 2026-08-02 ZIP must not be handed
  off again; a three-game exact-baseline regression precedes any replacement.

### JZ4740 real-hardware performance candidate

**Implemented and emulator-regressed (2026-08-02); physical FPS pending:**

- This candidate does not change the JZ4740 clock, PGM 20 MHz 68000 budget,
  8.468 MHz Z80 budget, 60 Hz game schedule or audio rate. It does not enable
  fixed frame skipping. Emulator host-yield and host-clock definitions remain
  restricted to emulator builds and are not evidence for this candidate.
- The 448x224 renderer now clears aligned H1 frame rows with MIPS `sw` stores
  instead of unaligned `swl`/`swr` pairs. Fully visible 32x32 background tiles,
  8x8 text tiles and sprites use row-pointer fast paths; only objects touching
  a viewport edge retain clipped bounds checks. Flip selection, stride
  multiplication and destination-row calculation were removed from inner
  pixel loops. Layer order remains high-priority sprite, background,
  low-priority sprite and text.
- The deterministic renderer fixture now covers 120 background cells, 1,653
  text cells, all four flip combinations, clipped edges and four sprites. The
  old and optimized implementations produce the same full-view FNV-1a hash,
  `25fd866152c476aa`, while preserving every 32-pixel stride guard. Five
  5,000-frame host runs had medians of 518 ms before and 322 ms after. This
  37.8% host microbenchmark reduction is directional renderer evidence, not a
  physical-H1 FPS result.
- A 256-entry read page table now covers the complete 5 MiB direct image, all
  sixteen mirrored 68000 main-RAM pages and the 64 KiB video-register page.
  Common A68K reads therefore avoid sequentially testing the sound window,
  ROM, main RAM, BG RAM, text RAM, row RAM, palette and video ranges. Rare I/O,
  partial pages and cross-page edge accesses retain the prior exact mapper.
- Palette writes increment a machine generation. The renderer skips its 2,304
  entry scan only when no 68000 palette write occurred; fades and scene changes
  still force a complete source comparison and RGB555-to-RGB565 refresh.
- The explicit `--jz4740-hardware` build profile also enables two previously
  isolated behavior-preserving options: it ends a 68000 slice only at the
  verified V119 IRQ wait (`PC 0x00103a96..0x00103a9d`, byte `0x806130 == 0`),
  and submits only the centered native 448x224 region rather than copying a
  480x272 application buffer each frame.
- The instrumented emulator candidate reached live battle and completed a
  90-second stress interval in one QEMU process with 111 movement/action
  inputs. Logical and rendered counters remained equal with zero skipped
  frames; ICS2115 sample-page faults, audio underruns and audio overruns were
  all zero. Held Escape returned to a correctly repainted desktop. This proves
  functional equivalence of the new memory paths, not physical performance.
- After palette generation tracking was added, the final-source emulator build
  repeated the boot fade, character montage, title transition and a live battle
  without stale colours. A further 60-second battle interval completed 74
  movement/action inputs with one unchanged QEMU PID, continuously advancing
  frames, zero fixed-frame skips, zero ICS2115 sample-page faults, zero audio
  submission failures and zero host audio underruns/overruns. Held Escape again
  restored the complete H1 game page. This remains a functional regression;
  physical-H1 FPS is still the acceptance measurement for this candidate.
- MXU remains out of this candidate. Palette-indexed transparent drawing does
  not map cleanly to the available packed arithmetic, and H1 firmware MXU
  enable/context-save behavior has not been established. IPU cannot compose
  PGM tile/sprite layers, while direct LCD DMA or cache-control takeover would
  conflict with firmware ownership. Those risks are not justified before the
  standard MIPS32R1 candidate is measured on the owner's H1.

**JZ4740 hardware-test handoff (2026-08-02):**

- `H1KOVJZ4740.bda`: 703,988 bytes, SHA-256
  `E1753524421A163DF36C992645BF119050DD928458ECAC70D0653977F40F63CC`.
- `H1-KOV-JZ4740-hardware-test-2026-08-02.zip`: 21,016,951 bytes,
  SHA-256
  `BF5D1219039205EE22B5F9850B0D901C45804EB09B6D21288C823B30057E995D`.
- Two consecutive release runs reproduced both hashes. The stage contained
  exactly three files and the archive top level contained only `A-root` and
  `游戏说明.txt`. Final stage and archive privacy scans reported zero findings.
- This is a KOV-only comparison candidate. It does not replace the accepted
  2026-08-01 BDA in the combined collection until same-scene physical-H1 FPS
  measurements show an improvement and gameplay remains stable.

### Guarded overclock and physical profiler

**Implemented and host-verified (2026-08-03); physical-H1 acceptance pending:**

- The new `--hardware-profile` build retains the native-view and verified V119
  IRQ-idle optimizations, then requests a temporary 408 MHz JZ4740 CPU clock.
  It first snapshots `CPCCR`, `CPPCR`, `CLKGR`, `I2SCDR`, `LPCDR`, `MSCCDR`,
  `UHCCDR` and `SSICDR`. A disabled/bypassed PLL, an unknown divider, an
  original CPU outside 250-432 MHz, or any unsafe peripheral divider rejects
  the change and leaves the machine at its original clock.
- The transition lowers memory/AHB/APB and active peripheral clocks before
  raising the PLL. Their target rates cannot exceed the rates calculated from
  the live startup registers. It does not alter SDRAM timings, CPU voltage,
  flash contents, firmware images, cache controls, DMA ownership, MXU or IPU.
  LCD, MSC and SSI are gated only during the register transition. Firmware
  clock state is refreshed through the V1.41 routine at `0x800042F0`.
- PLL lock and post-change CPU/memory/bus verification are bounded. Failed
  lock or verification restores the saved registers. Normal exit and all
  handled initialization/render/audio failures also restore them. A reset
  remains necessary after an unhandled crash because no application teardown
  can run in that case; the CPM change itself remains volatile and is not
  written to flash.
- Adaptive frame skipping compares the real firmware millisecond timer with
  the 60 Hz logical schedule. It skips only renderer and LCD submission while
  late, never 68000/Z80 cycles, input polling or ICS2115/audio generation, and
  forces a rendered frame after at most nine consecutive skips. This is not a
  fixed emulator-only skip mode.
- CP0 Count profiling records total and maximum time for A68K, Z80, PGM frame
  housekeeping, complete machine execution, rendering, audio, LCD submission,
  waiting and SD reads. It also records logical/rendered/skipped FPS, skip
  ratio and longest skip run, pack-page and tile-cache hit/miss counters,
  sprites/tiles/palette scans, ROM faults, all original/target clock registers,
  calculated rates, apply status and restore status.
- A normal held Back/Escape exit writes the ASCII report to
  `A:\应用\数据\KOVH1\KOVPERF.TXT` after restoring the original clock. Profile
  totals are CP0 Count values shifted right by eight per sample; maximum phase
  fields are explicitly named `*_raw_ticks` and remain unshifted.
- The 64-bit PLL arithmetic that initially introduced unavailable bare-metal
  `__udivdi3` was replaced with bounded 32-bit quotient/remainder arithmetic.
  Exhaustive host checks cover all 65,536 PLL M/N/OD combinations; the final
  MIPS ELF has no undefined symbols. The 11 KOV tests and full 72-test SDK suite
  pass. These results establish build and logic correctness, not H1 thermal
  stability or a physical FPS improvement.

The reproducible owner test package is built with:

```powershell
python scripts/build_kov_overclock_profile_test.py
```

It contains only `A-root` and `游戏说明.txt`, with `H1KOVPERF.bda` under the
application-program directory and the authorized `KOVH1.PAK` under
`A-root/应用/数据/KOVH1`. Stage and ZIP privacy scans are mandatory. The
2026-08-01 accepted combined package and rejected 2026-08-02 combined package
are not modified by this build.

**Initial profile-version-2 host/emulator verification (2026-08-03):**

- Two independent fixed-time release runs reproduced `H1KOVPERF.bda` at
  731,924 bytes with SHA-256
  `C5C5863463E859B83AE070E63CE87C0B5640146A3DFEEC687143241D90376E0D`
  and `H1-KOV-overclock-profile-2026-08-03.zip` at 21,027,738 bytes with
  SHA-256
  `E67C87267D4AD1EEA58993E3A61D429062CAA37DCA8EE2454A830F2500C2EB04`.
  The stage contained exactly the BDA, authorized PAK and operation guide.
  Both stage and archive-content/container privacy audits found zero issues.
- A private emulator-bridge build reached a live battle and completed a
  60-second action stress run in one QEMU PID. The frame stream advanced from
  1,317 to 2,510; audio stayed at 22.05 kHz with zero DMA underruns/overruns.
  At the detailed sample it had executed 8,074 logical frames, rendered 6,672,
  adaptively skipped 1,401, had five active ICS2115 voices, zero sample-page
  faults, 2,966 successful audio submissions and zero submission failures.
  A held-key exit restored the complete H1 desktop.
- The emulator exposes reset-like CPM placeholders (`CPCCR=0x00400008`,
  `CPPCR=0x28080011`) rather than a real H1 PLL state. The guard therefore
  correctly returned `clock_run_status=3` and did not apply 408 MHz. This
  validates the invalid-source path, not physical overclocking.
- A second run used an isolated writable NAND and successfully extracted the
  2,000-byte report after normal exit. It contained all profile-version-2
  clock, phase, frame-skip, storage, pack-cache and renderer fields, reported
  `clock_restore_result=0`, and measured 244 logical/rendered frames over
  4,072 ms (59.92 FPS) in that short static interval. The isolated NAND and
  all private debug outputs were removed after verification.

**Crash-persistent profile journal (2026-08-03):**

- Physical-H1 feedback on the first 408 MHz candidate showed a visibly faster
  first run for about 5-7 seconds followed by a reset. Four or five warm retries
  reset after about 2-3 seconds. No `KOVPERF.TXT` was present because profile
  version 2 created the file only from the normal held-Back exit handler. This
  is evidence that the clock change took effect, but it is not evidence of a
  stable 408 MHz operating point.
- The first physical-H1 profile-version-3 journal confirmed the failure
  boundary. The unit started at 336 MHz CPU and 112 MHz memory/bus, accepted the
  408 MHz plan, and read back 408/102/102 MHz with `status=1`, `applied=1` and
  `log_fail=0`. It then completed `ALLOCATED`, `PACK_READY`, `MACHINE_READY` and
  `RUNNING` at 3,459 ms, but reset before the first 1,000 ms `LIVE` checkpoint.
  No game frame became visible. Because `RUNNING` is emitted only after PAK
  validation, 68000/Z80/ICS2115 machine creation, renderer creation and audio
  opening, this excludes missing data and initialization failure. The reset is
  confined to the first sustained machine-frame workload at 408 MHz. Together
  with the shorter warm-retry lifetime, this is strong evidence that 408 MHz is
  unstable on this H1 CPU/power point under load; memory and bus were reduced
  below their original clocks and are not being overclocked. A reset remains
  volatile: the next launch again measured the original 336 MHz clock.
- Profile version 3 now creates and closes `KOVPERF.TXT` before preparing or
  applying the clock change. It appends `CLOCK_PLAN` before the transition,
  `CLOCK_APPLY_BEGIN` immediately before touching CPM, `CLOCK_RESULT` after the
  bounded apply/verification path, and named initialization stages. Once the
  main loop starts, one compact `LIVE` record is appended about every 1,000 ms.
  Each record is assembled in memory, emitted by one `fwrite`, and followed by
  `fclose`; no file handle is retained across frames.
- `LIVE` records include sequence/time, clock status and current CPM registers,
  logical/rendered/skipped frames, longest skip run, 68000 and Z80 PCs, active
  voices, sample faults, audio submissions, phase counters, pack-cache counts,
  renderer faults, and journal failures. Journal total/max CP0 Count fields
  quantify the logging overhead itself. A new launch intentionally truncates
  the old journal, so an abnormal-run file must be copied off the card before
  starting KOV again.
- The append path uses update-open (`r+b`, with `rb+` compatibility fallback),
  seeks to the H1-specific absolute end offset, writes one record, and closes.
  An isolated writable-NAND run reached the native KOV loop, produced audio at
  22.05 kHz with zero DMA underruns/overruns, and was stopped without invoking
  BDA teardown. The extracted 9,384-byte file retained 20 consecutive `LIVE`
  records from 1,695 through 20,762 ms and correctly had no `FINAL_REPORT`.
- The temporary emulator-only bridge BDA, isolated NAND, extracted runtime
  journal, screenshots, and deployment reports are test artifacts and are not
  release contents. The release candidate retains the same 408 MHz plan,
  verified V119 IRQ-idle exit, native 448x224 submission and adaptive frame
  skipping as profile version 2; this change does not lower the requested CPU
  clock or alter the renderer/audio/game logic.
- The final profile-version-3 `H1KOVPERF.bda` is 748,932 bytes with SHA-256
  `FC491888874DB46EDCD05E054616657E39A910D20488FBEDC0B6E0FF8FF881F2`.
  `H1-KOV-overclock-profile-2026-08-03.zip` is 21,034,956 bytes with SHA-256
  `A32D6FA75181E9ECB66F995C4DC047D1BE448D17AC119B26460AD7F4C6ADA426`.
  The release builder reproduced the BDA byte for byte, all 11 KOV and 72 SDK
  tests passed, and the archive contains exactly the BDA, authorized PAK and
  operation guide beneath the permitted `A-root`/guide top level. Mandatory
  scans of both the three-file stage and ZIP reported zero privacy findings.

**Exact release-artifact emulator verification (2026-08-03):**

- A clean isolated 1 GiB H1 NAND was populated with the exact release files at
  `/\u5e94\u7528/\u7a0b\u5e8f/\u9ed1\u767d\u5b50.bda` and `/\u5e94\u7528/\u6570\u636e/KOVH1/KOVH1.PAK`. The
  BDA was 748,932 bytes with SHA-256
  `FC491888874DB46EDCD05E054616657E39A910D20488FBEDC0B6E0FF8FF881F2`;
  the owner-authorized PAK was 58,785,792 bytes with SHA-256
  `6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53`.
  Both NAND deployments passed byte-for-byte readback and the resulting FTL
  scan contained no invalid or torn records. The release BDA itself did not
  contain or depend on the emulator-only resource bridge.
- The first run reached the blue-cloud intro and a live battle. Audio remained
  at 22.05 kHz with zero emulated DMA underruns or overruns, and the QEMU PID
  remained responsive for more than seven minutes. However, framebuffer
  submissions stopped at sequence 1,337 and the journal stopped at 142,778 ms
  while QEMU and the audio DMA continued. The last record reported 8,521 logic
  frames, 7,349 rendered frames and 1,172 skipped frames. This is an
  application-level long-run stall reproduced with the exact release payload;
  it is not a QEMU process crash and remains an open emulator finding.
- Stopping QEMU without BDA teardown preserved a 63,090-byte journal with 141
  consecutive `LIVE` records, sequence 7 through 147 and time 1,753 through
  142,778 ms. It contained no `FINAL_REPORT`, no sequence gaps, no NUL padding
  and no nonzero `log_fail` value. This verifies that the incremental append,
  close and FAT/FTL commit strategy survives a reset-like stop.
- A fresh second launch intentionally replaced the old journal, reached the
  intro and battle, and exited to the H1 desktop after Back was held for 1.3
  seconds. Its 22,638-byte journal contained 45 consecutive `LIVE` records,
  sequence 7 through 51 and time 1,202 through 45,539 ms, followed by
  `FINAL_REPORT`. It reported `clock_restore_result=0`, no logging failures and
  no NUL padding. The emulator's placeholder clock registers again produced
  guarded status 3, so no 408 MHz transition was attempted in this host test.

**384/336 MHz physical comparison packages (2026-08-03):**

- The unstable 408 MHz candidate was replaced by a guarded 384 MHz target.
  The target uses the exact JZ4740 PLL points `(M,N,OD)=(62,0,0)`,
  `(190,4,0)` or `(254,2,1)`, keeps memory and bus at or below their measured
  112 MHz startup rates, and retains the crash-persistent incremental journal.
- `H1-KOV-384MHz-profile-2026-08-03.zip` is 21,034,960 bytes with SHA-256
  `880451E4D5C097608F00D2B3C3487DB2F1615543C812B209D4DF40FA59E35B59`.
  Its `H1KOVPERF.bda` is 748,932 bytes with SHA-256
  `7E11E496E1200A5F2C346D25E0DDA0DD5A622AADB7DA53F739D21F5AF32E4D11`.
- `H1-KOV-336MHz-profile-2026-08-03.zip` is 21,034,961 bytes with SHA-256
  `7E6ED637713BE0E330720309B96B2E4F0686958FB6468D8E563CB87DAAA99AFE`.
  Its `H1KOVPERF.bda` is 748,932 bytes with SHA-256
  `783BF5CFE6722C2BB685305C4035F01D495190513E01AAAF1DEC7CC137509FF0`.
- The 336 MHz package compiles the same hardware-profile, adaptive-frame-skip
  and journal code but requests the stock 336 MHz target. On a normal H1
  startup the clock planner returns `KOV_CLOCK_ALREADY_FAST` and leaves CPM
  registers unchanged, providing a controlled baseline for the 384 MHz test.
- Both packages contain exactly `A-root`, the authorized `KOVH1.PAK`, one BDA
  and the operation guide. Two fixed-time builds of each target reproduced its
  BDA byte-for-byte; all 11 KOV and 72 SDK tests passed. Stage, archive-content
  and archive-container privacy scans reported zero findings.

**Fixed-slot journal V4 and repeated long-run stall (2026-08-14):**

- `KOVJOURNAL4:FIXED_SLOTS` preallocates `KOVPERF.TXT` as 64 fixed 768-byte
  records (49,152 bytes). Slot 0 contains the format marker; slots 1 through 63
  form a circular record area. Five-second live checkpoints use only absolute
  seeks and never grow the file. End-relative output remains only in the normal
  final-report path.
- Base, 336 MHz and 384 MHz BDA profiles were rebuilt reproducibly. Their
  sizes/hashes were respectively 703,812 bytes / `162BB9F0AD2D573F4C625A2E97B89984DE9176FA68D5E38EEDAEEB597E98AF7F`,
  749,860 bytes / `E360EAD02A25BAE9AE00435EB400E370D7C4C052BD3FDAA04B05C7CD41EBB7E0`,
  and 749,860 bytes / `C6A6DA9CE75E43D21C20CFA7BF970A8239561179CD9EC283B42C31EF2841334A`.
  All three passed BDA structure, no-ROM and privacy checks.
- An isolated 336 MHz-equivalent NAND run reached the blue-cloud intro. Its
  exact 49,152-byte journal contained continuous sequence numbers `0..34`, 28
  live records from 5,486 through 140,486 ms, and `log_fail=0`. The last live
  state reported 8,400 logical frames, 8,388 rendered frames, 12 skipped
  frames, no sample faults, no audio submission failure, and 68000 PC
  `0x0013b25e` in each of the final eight samples.
- Game progress and journal checkpoints again stopped around 140 seconds while
  QEMU and host audio continued. Because this closely reproduces the earlier
  142,778 ms boundary without file append or growth, FAT write amplification is
  not the root cause. The next diagnostic must distinguish a blocked native
  MIPS path from a stable 68000 wait state and instrument render, present,
  audio, storage, and main-loop progress at the boundary.

**V5 clock correction and V6 real-H1 frame profiles (2026-08-17):**

- V5 removed the private 1 ms timer from the KOV runtime and derives frame
  pacing, held-key timing and journals from the firmware's free-running 80 Hz
  tick. The emulator-only host monotonic clock and cooperative sleep remain
  behind `H1_KOV_EMULATOR_HOST_YIELD`; they are timing-correction tools, not
  real-H1 performance evidence.
- V6 generalizes fixed rendering cadence as `H1_KOV_FIXED_SKIP`. A value of one
  executes every 68000/Z80 frame, input poll and audio submission, but skips
  every other renderer and LCD submission. The target is approximately 60
  logical updates and 30 rendered frames per second without slowing gameplay.
- Five reproducible profiles are included. Base, adaptive 336 MHz, fixed-30
  336 MHz, adaptive 384 MHz and fixed-30 384 MHz have respective SHA-256 values
  `627495DEF00612B75182991C8FFD7AB3B6A356956DC16304819B344AB76A3941`,
  `1DA1A7F773B8BE70ADEE1029591C8FF512FBCD5D0C991BA30B8397C50543B344`,
  `8A00EFE17E6D2BFF4C3F2B8A7BF13FDDA2624E6EE71544F957D6340DB15861E6`,
  `22EFA974B791FC530F4405307D5352B561AF79885A7FB70FA1D37DE930572CE9`
  and `BC9C96EF3BB120E732C6A1BE9A733CFB3CAE5769A08AA3BC475B7D01E88E86BE`.
- Every BDA passed structure, icon and Chinese-title validation. Direct binary
  checks found no host-yield capability, asset-bridge magic or host-pacing
  marker. All 16 KOV tests and 34 core SDK tests passed.
- An instruction-clock emulator smoke test launched the fixed-30 336 MHz BDA
  to the real KOV title, accepted coin/start/direction/action inputs, produced
  22.05 kHz audio with zero underruns/overruns and stopped cleanly. This is only
  a functional regression; its frame rate is intentionally not reported as a
  real-H1 result.
- `H1-KOV-Plus-performance-v6-2026-08-17.zip` is 348,587 bytes with SHA-256
  `FD5485321511CC6BBC12B0D3ADF330F4B3013C5EE1A3B36D24446B89AC730DB1`.
  Its eight staged files and the ZIP container independently passed the release
  privacy audit with zero findings.
- Real-device acceptance requires `KOVPERF.TXT` from the same busy battle for
  adaptive and fixed-30 profiles at 336 and 384 MHz. `logic_fps_x100` measures
  gameplay speed; `render_fps_x100` measures visual cadence. Phase percentages
  determine whether the next optimization belongs in A68K, Z80, rendering,
  audio or LCD submission.

**V7 active-voice ICS2115 mixer candidate (2026-08-17):**

- IDA inspection of the V6 MIPS ELF confirmed that the 22.05 kHz mixer scanned
  all 32 ICS2115 slots and rebuilt frequency step, volume, sample base and loop
  boundaries for every active sample. The core is a generated MIPS32R1 A68K
  interpreter, not a JIT; the C build already uses `-O3`, `-march=mips32`,
  soft-float, non-PIC code and section garbage collection.
- V7 gathers active voices once per audio buffer and retains their invariant
  mixer values in scratch storage owned by the heap-allocated ICS2115 object.
  Sample callback order, 22.05 kHz output, address progression, completion
  flags and IRQ behavior are unchanged. The final MIPS mixer stack frame is 80
  bytes, compared with 72 bytes in V6; an earlier stack-resident draft was
  rejected because it required about 1 KiB of additional task stack.
- A two-voice continuous-play regression covers output samples, read counts,
  address progression and active state. All 16 KOV tests and 34 core SDK tests
  pass, including the MIPS32R1 cross-compile.
- A five-voice host microbenchmark performed 36,800,000 reads with the same
  checksum in both versions. Five interleaved runs measured medians of 293 ms
  for V6 and 164 ms for V7, a 44% mixer-only reduction on the host. This does
  not establish the physical-H1 FPS gain.
- V7 hardware logs identify the implementation as `audio_mixer_version=2`.
  Acceptance requires a same-scene V6/V7 comparison, preferably fixed-30 at
  336 MHz first. Emulator smoothness remains functional evidence only.
- The five reproducible V7 profiles (base, adaptive 336 MHz, fixed-30 336 MHz,
  adaptive 384 MHz and fixed-30 384 MHz) have respective SHA-256 values
  `B6B99829E9A63910034A7D34733631A04C1B815D9516AE898FB7763C9A566178`,
  `370AF5202F553EBF2D6D7B9CC96EC85E576FECAEF93595803471E791A323D5BC`,
  `A9E49223D1ADD92ECF99BB75321248209501FCF353C6F2F37C9FF5F0631E3789`,
  `84BC0C065531CC08E81730BC9998A3E2596CA0C8C7308612BD4931C96732BC01`
  and `9E4B124D3405EC0FB0CC2C4436E807854E6533E4AE292B947FDF9CFF4BA5FF1C`.
- The exact fixed-30 336 MHz release BDA was transactionally installed as the
  only `KOV.bda` on an isolated writable NAND. It reached a live battle and
  accepted coin, start, direction and action input. Host audio stayed at 22.05
  kHz with zero underruns or overruns. The QEMU process used 64 MiB, single-
  thread TCG and instruction-clock pacing; no emulator performance increase
  was used as evidence for the H1.
- A reset-like stop preserved the complete 49,152-byte journal. Its 30 `LIVE`
  records had continuous sequence numbers `7..36`, ran from 5,825 through
  150,987 ms and all reported `audio_mixer_version=2`, phase 8, zero sample or
  ROM faults, zero failed audio submissions and `log_fail=0`. The final record
  reported 8,734 logical frames, 4,367 rendered frames and 4,367 skipped
  frames. The NAND scan contained no bad, invalid or torn FTL records.
- LCD submissions and journal checkpoints then stopped while QEMU guest
  instructions and emulated audio continued. This repeats the known long-run
  emulator-only application stall near the prior 140-143 second boundary; the
  clean V7 journal gives no evidence that the mixer change caused it.
- `H1-KOV-Plus-performance-v7-2026-08-17.zip` is 350,410 bytes with SHA-256
  `8554513F1FC54D291273F1A6D441037A0DD6A7C0057631BFE043D13F1AB75E84`.
  Its eight staged files and ZIP container independently passed the privacy
  audit, and 7-Zip verified the archive without errors.

**Final public build (2026-08-01):**

- `H1KOVPlus.bda`: 702,452 bytes, SHA-256
  `09C8E9CC68712F1E59ED0BD86AFFC4B5D4D6B715BBE5B6A0386FB08AF9CCE5BA`.
- `KOV-Plus-H1-2026-08-01.zip`: 58,679 bytes, SHA-256
  `ADC3E73FA095B9F55F3FB1FF07D4B8EA49507672D2634C1F1C8AF517D8234181`.
- The four H1 icon resources passed structural, colour-count and placeholder
  rejection checks. Their combined resource SHA-256 is
  `F32A053635B58C989C5859F9CEDD9AC9E906D883C5781769821E9A894DAF75AD`.
- Two consecutive fixed-time builds produced the same BDA and ZIP hashes.
- The final combined privacy scan covered 56 relevant source and artifact
  files with zero findings. Generated Python bytecode caches were removed and
  the release builder now disables bytecode generation for child tools.
