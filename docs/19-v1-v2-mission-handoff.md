# V1 Mission on V2: Handoff State

This document records the current handoff state. It uses repository-relative
paths only and contains no host-specific paths, credentials, emulator logs, or
IDA databases.

## Executive Summary

The complete V1 Mission payload is present and readable, but it has not yet
been demonstrated to reach a working Mission GUI loop on the V2 system. The
compatibility wrapper is built and BDA validation passed; the final runtime
test was intentionally stopped for handoff.

The apparent data loss and the blank Resource Explorer are not caused by
corrupted Mission files. The direct cause is a FAT geometry mismatch: the
expanded test image uses the larger V1 geometry, while V2's dynamic font and
resource code expects the V2-native geometry. V2 can boot the larger image, but
dynamic labels and directory text fail. A global kernel `A:` to `B:` path
replacement was also tested and produced a black screen, so it is not a valid
fix.

## Verified Facts

- The complete files are present in `work/v2-mission-full-native.raw`:
  - `应用/程序/使命.bda`
  - `应用/数据/游戏/LYXZ/DataLib.dat`
  - `应用/数据/游戏/LYXZ/DataLibIndex.dat`
- FAT16 extraction finds the Mission BDA and both complete DataLib files.
- `HZK_LIB.BIN`, `26字母.bin`, `DiyRes.dlx`, and `touchpanel.dlx` have
  byte-for-byte matching SHA-256 hashes between the source tree and the full
  test image.
- The V2-native image `work/v2-v1-game-compat-test.raw` has `824288` total
  sectors and renders the desktop, dynamic labels, and Resource Explorer
  correctly.
- The full Mission image `work/v2-mission-full-native.raw` has `2001376` total
  sectors. This is the larger V1 geometry despite retaining the V2 volume
  label. On this image prebuilt desktop labels render, but dynamic labels
  become vertical white bars and directory text appears blank.
- Resource Explorer showing only `B:` is expected for the internal NAND volume;
  it does not prove that Mission data are absent.

## Compatibility Work Completed

`h1-bda-sdk/examples/v2/v1_game_stage.c` now builds a storage-geometry shim:

- reserves `0x83E03000` for a copied FS compatibility table;
- installs `compat_fs_get_info` at FS offset `0x048`;
- returns conservative virtual geometry satisfying Mission's capacity check;
- restores the original GeneralDLTable FS pointer after the game returns; and
- records the call in the existing trace buffer.

`scripts/build_h1_v2_mission_compat_map.py` records FS+`0x048` as
`shim_storage_geometry`. The experimental wrapper is
`work/analysis/mission-fsfix.bda`; it embeds the original Mission payload and
passed BDA validation.

The wrapper has not completed a GUI-loop runtime test with both complete
DataLib files. The next compatibility point is the V1 FS-open service
(FS+`0x000`), preserving the V2 file-handle ABI and rewriting only a leading
`A:\\` prefix to `B:\\`. This is separate from the implemented geometry shim.

## Failed Experiment

`scripts/patch_h1_v2_drive_paths.py` performs an auditable equal-length
replacement of literal `A:\\`/`a:\\` prefixes in the decoded V2 kernel. The
patched kernel stopped at a black screen. Do not use global path replacement
as a release fix; path translation belongs in a scoped FS shim.

## Emulator State at Handoff

Only port `8793` was used for the final user-visible investigation. The last
known-good configuration used the V2-native image, 64 MiB RAM, single-threaded
TCG, and no host-paced speed-up. All QEMU test processes have been stopped;
no emulator is intentionally left running for manual inspection.

## Recommended Next Steps

1. Keep V2's native FAT geometry and provide the complete Mission tree through
   a V2-compatible second volume or SD backend; do not expand the internal FAT
   to the V1 geometry.
2. Confirm whether the existing JZ4740 MSC/SD model can connect an additional
   block backend. Relevant sources are under
   `work/rebuild/qemu-11.0.0/hw/sd/jz4740_msc.c` and
   `work/rebuild/qemu-11.0.0/hw/mips/bbk9588.c`.
3. Add the FS-open shim, then run one minimal 8793 probe: verify the FS result,
   GUI initialization events, and successful opens of both complete DataLib
   files. Do not change CPU timing or enable emulator-only acceleration.
4. Before any release or handoff archive, run
   `python scripts/audit_release_secrets.py` against the archive itself.

## Constraints

- Keep both complete Mission DataLib files for every validation image.
- Do not delete project files directly. Use the Windows Recycle Bin for cleanup.
- Do not ship usernames, host names, absolute paths, Codex data, credentials,
  IDA databases, runtime logs, or debugger logs.
- Do not include temporary emulator state in release packages.
