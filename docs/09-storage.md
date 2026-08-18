# Workspace storage and artifact policy

Last updated: 2026-08-18 (Asia/Irkutsk)

## 2026-08-18 source-project split cleanup

The workspace was reduced while materializing the independent `systems/1.X`
and `systems/2.X` source projects. A checked-in cleanup script,
`scripts/recycle_h1_transients.ps1`, resolved every target inside the workspace
and moved it to the Windows Recycle Bin. No project file was permanently
deleted.

The cleanup selected 367 obsolete or reproducible targets totaling
24,176,284,352 bytes (22.516 GiB). These included superseded NAND copies,
Mission geometry experiments, extracted QEMU/toolchain trees, compiler and
Python caches, old captures, logs, and duplicate release/test directories.
Running the same script again with `-WhatIf` selected zero targets.

Post-cleanup logical sizes are:

```text
work/:           2,549,088,255 bytes (2.374 GiB)
whole workspace: 6,777,147,502 bytes (6.312 GiB)
```

The retained canonical inputs and runtime state were hash-checked after
cleanup: both V1.41 archives, both official V2.20 packages, the canonical V1
NAND, the V2 runtime-probe NAND, and the current V1-game-on-V2 compatibility
NAND. The private source area, publication checkouts, deliverables, and both
new system project trees remain present. No workspace QEMU or Python research
process remained active.

This section supersedes older size and retention snapshots below. Future
milestones keep only the current canonical image plus the minimum evidence
needed to reproduce the conclusion. Cleanup remains recoverable through the
Recycle Bin until the user empties it.

## 2026-08-18 Recycle Bin verification

Before permanent user cleanup, the Windows Recycle Bin was inspected read-only.
All 190 visible entries originated in this workspace; no unrelated user file
or directory was present. Their physical payload size was 14,321,131,955 bytes
(13.338 GiB):

| Class | Items | Bytes | Decision |
| --- | ---: | ---: | --- |
| superseded NAND experiments | 9 | 13,287,555,072 | redundant with the retained canonical V1, V2, and compatibility images |
| derived extraction/release/debug directories | 5 | 1,014,569,596 | reproducible from retained inputs and tracked source |
| generated V2 screenshots and framebuffer captures | 173 | 18,907,207 | conclusions are documented; captures are reproducible |
| Python/pytest caches | 2 | 94,020 | regenerated automatically |
| one-time GitHub transport helper | 1 | 6,060 | no longer needed after exact remote commit verification |

The complete Mission payload was checked before declaring the expanded tree
redundant:

- `DataLib.dat`: 157,063,229 bytes, SHA-256
  `4E67278C6E5EED5E650E470E788D8BF0C7DE9436F07815AF2DA7A35EEFBC3DE5`;
- `DataLibIndex.dat`: 180,216 bytes, SHA-256
  `7852C4199EA2B7A6D1990DE540844FFDA6A24D2930D6EDF79C477146582A2F79`;
- the staged `使命.bda`: 529,172 bytes, SHA-256
  `C103600D5BAED496E8FF7C23FB8FD204731F76B838074689543A150B0A4F9283`.

The two DataLib hashes match files read directly from the retained canonical V1
NAND. The staged BDA hash matches both retained standalone copies. Critical V1,
V2, and compatibility NAND hashes and both official V2.20 package hashes were
also rechecked. The warning in `14-rebuild-status.md` about the two root V1 RAR
files remains in force; this redundancy conclusion relies on the verified V1
NAND, not on treating those RAR files as trusted archives.

The original recycle operation reported 24,176,284,352 bytes, while only
14,321,131,955 bytes remained visible at this audit. The approximately 9.178 GiB
difference is no longer represented in the Recycle Bin, consistent with Windows
capacity eviction during a very large recycle operation, and is not recoverable
from the current bin. Every item that remains visible is redundant and may be
permanently removed by the user.

## Storage incident check

The workspace was inspected after it reached 9.577 GiB under `work/`. No QEMU
process was running and no file was still growing. The three live processes
were the expected `idalib-mcp` launcher and its Python workers. This rules out
an emulator write loop or a leaked image-building process.

The size came from intentionally retained but duplicate build artifacts:

| Area before cleanup | Bytes | GiB |
| --- | ---: | ---: |
| `work/tools` | 4,448,809,410 | 4.143 |
| `work/emulator` | 3,387,858,374 | 3.155 |
| extracted PC/SD recovery inputs | 2,366,165,470 | 2.204 |
| analysis and small staging files | 80,132,610 | 0.075 |

Status: **confirmed not to be a runaway-write bug**.

## Cleanup performed

The following reproducible files were removed:

| Artifact class | Bytes removed | Recovery |
| --- | ---: | --- |
| empty 1 GiB FAT image, two 512 MiB NAND images, old 117.5 MiB QEMU log | 2,255,188,500 | rebuild with repository scripts and rerun the guest |
| MSYS2 pacman package cache | 309,357,948 | download packages again |
| already-extracted QEMU/MSYS2/9588/innoextract archives | 241,680,592 | download archives again |
| extracted logical volume and standalone FAT16 image used by `fsck.fat` | 2,049,425,408 | regenerate from the retained NAND baseline and extraction scripts |
| **total** | **4,855,652,448** | |

After cleanup, `work/` is 7,476,738,824 bytes (6.963 GiB). The whole workspace,
including both untouched original firmware RAR files, is 8,392,529,190 bytes
(7.816 GiB). C: had 172.07 GiB free at the end of the check.

## 2026-07-23 second audit and cleanup

The user clarified that the virtual machine has only about 5 GB of practical
remaining capacity and that the large free-space value reported for C: is not
usable for planning. A complete recursive logical-size audit found:

```text
work/:           8,659,273,887 bytes (8.065 GiB)
whole workspace: 9,575,279,359 bytes (8.917 GiB)
```

Only the two active 1,107,296,256-byte NAND images remained under
`work/emulator/`: `h1-1g-a5-template.raw` and `h1-1g-a5-system.raw`. The failed
`h1-1g-a5-template-fixed-run1.raw` control copy was already absent. No QEMU,
copy, Ninja, or image-builder process was active. The additional live Python
workers belonged to the two expected IDA MCP sessions.

The following reproducible directories were then deleted after their absolute
paths, ordinary-directory status, and sizes were checked:

| Deleted area | Bytes | Recovery |
| --- | ---: | --- |
| extracted duplicate PC recovery EXE under `work/pc` | 467,351,076 | extract the untouched root RAR again |
| unused QEMU `roms` source submodules | 545,262,534 | download/extract QEMU source again; not needed by either configured MIPS build |
| three superseded build directories | 47,894,581 | rerun the documented configure/build process |
| Python bytecode cache | 185,296 | regenerated automatically |
| **second-audit total** | **1,060,693,487** | |

After this cleanup the whole workspace measured 8,514,585,872 bytes
(7.930 GiB), of which `work/` was 7,598,580,620 bytes (7.077 GiB). The original
firmware archives, extracted SD/PC payload inputs, two active NAND images,
analysis reports, IDA databases, source overlay, patched QEMU source, current
ARM64 validation build, and current x86-64 delivery build were preserved.

Status: **confirmed not a runaway-growth bug; the excess was recoverable
duplication and obsolete build output**. Future capacity decisions use the
user-supplied 5 GB practical headroom, not the virtual C: free-space report.

## 2026-07-23 calibration-output cleanup

After the successful full-system boot was documented, the incomplete `cal1`
capture and the rejected `cal5` swipe experiment were no longer needed. Their
two capture directories, screenshots, register logs, and empty process logs
were deleted. This removed 261,315 bytes. The accepted `cal2`, `cal3`, and
`cal4` framebuffer evidence remains intact.

The post-cleanup recursive logical sizes are:

```text
work/:           7,599,391,365 bytes (7.077 GiB)
whole workspace: 8,515,237,839 bytes (7.930 GiB)
```

No matching `h1-system-fixed-cal1*` or `h1-system-fixed-cal5*` artifacts remain.
Future failed frame/gesture probes follow the same rule: record the conclusion
first, then remove the reproducible capture output before starting the next
experiment.

## Retention rule

Keep the two user-provided firmware archives, extracted recovery inputs,
analysis databases/reports, source overlays, patched QEMU source, the x86-64
release build, the ARM64 development-validation build, `h1-boot-nand.raw`,
`h1-1g-a5-template.raw`, and `h1-1g-a5-system.raw`.

Do not retain package-manager caches, downloaded archives after successful
extraction, unbounded instruction traces, obsolete writable NAND copies, or a
standalone full-size FAT staging image. New image tooling should write FAT data
directly into the final NAND/FTL output or use sparse temporary storage. Runtime
tests should use QEMU snapshot mode whenever persistence is not the subject of
the test. If a writable 1.1 GB control is required, write its scan/hash report
first and delete the raw copy immediately after the conclusion is established.

## Active workspace allowance

On 2026-07-23 the user initially authorized up to 20 GB of additional workspace usage.
The new baseline immediately before touchscreen calibration was
9,739,211,101 bytes (9.070 GiB) under `work/`, with about 170 GiB free on C:.
The increase from the post-cleanup figure is the finalized 1 GiB system NAND
plus one writable QEMU calibration copy, not ongoing growth. Build and test
artifacts may remain within this allowance until their acceptance milestone;
superseded writable NAND copies and logs are then removed under the retention
rule above.

After the FAT consistency check completed on 2026-07-23, the two approximately
1 GiB staging images were deleted. `work/` then measured 9,758,918,033 bytes
(9.089 GiB), and C: had 169.87 GiB free. Their reports and the clean retained
`h1-1g-system.raw` baseline remain available; no required reverse-engineering
evidence was removed.

This allowance was later superseded by the user's explicit statement that only
about 5 GB is practically available inside the Windows 11 VM. The current
policy is therefore to keep peak additional use below 5 GB and to avoid any
unnecessary full NAND copy.
