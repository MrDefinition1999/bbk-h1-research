# Focused rebuild scope

Updated: 2026-08-04

## Active deliverables

Only the following deliverables remain in scope after the storage incident:

1. The native BBK H1 BDA SDK and its H1-specific examples and documentation.
2. The x86-64 Windows BBK H1 emulator, including the web controls and JZ4740
   hardware models.
3. The native H1 KOV Plus port, its ROM-free source/build chain, physical-H1
   performance profiles, and incremental crash journal.

The Dingoo A320 game ports, DOOM, GTA, and CS 1.5 are abandoned. They are not
release inputs and are not part of current validation. Their retained working
files are historical material only.

## Confirmed post-incident state

- The x86-64 QEMU executable is reproducibly finalized as QEMU 11.0.0, PE
  machine `0x8664`, SHA-256
  `71D262B5ABEA05E96F98C7B379677C820A540EF54922EAB9AF4354409D3E3302`.
- The portable x86-64 Python runtime and browser frontend pass isolated startup
  and HTTP smoke checks.
- The SDK core format, builder, validator, deployment, service-scan, and H1
  frontend tests are maintained independently of the abandoned ports.
- The KOV port has a ROM-free deterministic build and host/MIPS regression
  suite. A private playable pack cannot be rebuilt without the original ROM
  archives.

## Current focused verification

Verification on 2026-08-04, after excluding every abandoned port:

- H1 SDK core: 31/31 tests passed. This covers BDA headers/resources, native
  multi-source builds, path-prefix mapping, NAND deployment growth, H1 input
  calibration detection, service-table scanning, and BDA validation.
- KOV: 11/11 tests passed with zero skips. The missing
  `tests/test_bootstrap.py` source was reconstructed from its matching C
  runner and accident-era bytecode behavior. The suite covers the clean-room
  68000 bootstrap, V119 decryption and IRQ-idle signature, ASIC28, JZ4740 clock
  planning, ROM-pack paging, layer/cache rendering, ICS2115 audio, and actual
  MIPS32R1 compilation.
- SDK release: the Hello and memory examples were each built twice with
  identical bytes and zero privacy findings. The deterministic 88-file SDK
  archive has SHA-256
  `E8ADD03AC1A64F458A6FB57C04AB6D6B068D2CFEA695A42B252E0C6F0B640CAB`.
  Its staging tree and ZIP both passed the release-secret audit, it contains
  no abandoned port paths, and all 29 packaged tests passed after extracting
  the ZIP into a clean directory.
- KOV ROM-free release: two complete builds produced the same archive,
  SHA-256
  `06CE94186E188CA1734BD04730585F1DE79FAFBC69EDE8C70DE38EE2C4317AD1`.
  The BDA is 703,812 bytes, its four icon resources passed validation, and
  staging/archive privacy audits reported zero findings.
- KOV hardware profiles: independent 336 MHz and 384 MHz BDA builds are each
  byte-reproducible. Their SHA-256 values are respectively
  `993309873B02C4EFD6DD88445ED6BFF492DDB65CF3C1AC9499364B01574FBD4B`
  and
  `05AA509CD0B2C14E9EDDA086FC880455C41A7E1D2A57C2C2A56D4572603E22DE`.
  Both retain the version-3 incremental journal and final-report markers and
  passed binary privacy scanning.
- KOV source release: the reproducible source package is limited to the native
  H1 port, the minimum H1 BDA SDK build components, and the reviewed A68K/CZ80
  CPU sources. It excludes the abandoned A320 ports, CS, DOOM, ROM data,
  firmware, compiler binaries, caches, logs, and Git metadata. CZ80 remains
  restricted to credited non-commercial use under its bundled upstream readme.
  Two complete release builds produced the same 383,501-byte archive with
  SHA-256
  `B8F438249FBF8CD8AB25939AC8E4CC20CC2C73BB75ADAA6703736D14F1C70822`.
  Both staging and ZIP privacy audits reported zero findings. After clean ZIP
  extraction, all 11 KOV tests passed without skips and all three profiles
  rebuilt twice with identical bytes. The packaged profile SHA-256 values are:
  base `162BB9F0AD2D573F4C625A2E97B89984DE9176FA68D5E38EEDAEEB597E98AF7F`,
  336 MHz `4335157CA5FFDB281BEC898D6F79856F6E9EC7EC3C68922620BE19F3A625087C`,
  and 384 MHz
  `A15565A5CAFA1AC2AC0DAF0F2D9CD79C9962B48EA00A3EC245E77CE941787442`.
  Compared with the earlier validated BDA samples, their MIPS payloads from
  offset `0x785C` onward are byte-identical; only 3/6 BDA header bytes differ.
- Emulator runtime: the finalized QEMU remains 10,544,640 bytes with SHA-256
  `71D262B5ABEA05E96F98C7B379677C820A540EF54922EAB9AF4354409D3E3302`;
  isolated execution reports QEMU 11.0.0 and exposes `bbkh1`. All 37 top-level
  runtime PE files are x86-64. JZ4740 ECC tests passed 3/3 and frontend tests
  passed 4/4, including calibration recognition, six permanent keys, the
  38-key drawer, and the default-disabled retired A320 bridge.
- Emulator packaging: the 660-file runtime-only ZIP is deterministic with
  SHA-256
  `691D83E0A15A3F6016D6F4B4027A3F395B729499238DC6F9919381BE8EC9415F`.
  It contains no firmware, PAK, A320 assets, abandoned-port filename, cache, or
  log. Staging and ZIP audits reported zero findings. After extracting it, the
  bundled Python served both the frontend and audio worklet with HTTP 200;
  shutdown left zero listeners, QEMU processes, and project Python processes.

## Recovered trusted inputs

The official V1.41 PC and SD archives were downloaded again from the BBK
support site and passed archive integrity checks. Their SHA-256 values match
the pre-incident trusted values:

- `@ibox H1 V1.41CJXTHF.rar`:
  `B1F5F4D886C1C08C7D6F0722581615A7262CFE44B62F1F1E47EEF204F5E5E5DB`
- `H1 V1.41SDKHF.rar`:
  `DFEA2563EF6770BA6E30E8006767DB6E7542C59D63CDECD05B266515D94A5A0C`

The seven owner-provided cartridge ZIP archives under `kov/` also match their
trusted per-file hashes. They rebuilt `KOVH1.PAK` as 58,785,792 bytes with
SHA-256
`6A3E5EF41212AA47A242689D904374DF0CBFEF4E34313053B2D7C1755642DB53`.

The reconstructed V1.41 stock and KOV NAND images both completed automatic
calibration and reached the desktop under the x86-64 emulator. The KOV image
then launched the native 448x224 game view, produced 22050 Hz audio, accepted
Start/direction/action input, and returned to the desktop by holding Esc.

## Release rule

Every handoff must be rebuilt from sanitized source through checked-in scripts.
Both staging trees and final archives must pass
`python scripts/audit_release_secrets.py`. Local user names, host names,
absolute profile/workspace paths, credentials, caches, logs, reports, nested
Git metadata, and private ROM inputs are release blockers.
