# Raw NAND image construction

Last updated: 2026-07-22 (Asia/Irkutsk)

## Purpose

`scripts/make_h1_nand.py` converts the three files written by the H1 SD-card
recovery application into a page-and-spare raw NAND image suitable for the H1
QEMU machine. It reproduces the recovery program's padding, physical offsets,
spare markers, and JZ4740 Reed-Solomon ECC rather than concatenating the input
files as plain data.

The builder leaves gaps and unused pages erased (`0xFF`) and verifies every
programmed page, including its OOB bytes, after writing it. It also checks
selected boundary pages that must remain erased.

## Geometry and format

| Property | Value |
| --- | ---: |
| data bytes per page | 2,048 |
| spare bytes per page | 64 |
| raw bytes per page | 2,112 |
| pages per erase block | 128 |
| physical blocks in boot-area image | 62 (`0x3E`) |
| raw image bytes | 16,760,832 |

Every programmed page uses spare prefix `FF FF 00 00 00 FF`; four nine-byte
RS parity fields begin at spare offset 6. See
[04-system-recovery.md](04-system-recovery.md) for the recovery-code evidence.

## Confirmed segment layout

| Segment | Start page | Pages | Programmed bytes | Source bytes |
| --- | ---: | ---: | ---: | ---: |
| `loader.bin` | `0x000` | 3 | `0x1800` | 5,016 |
| `u-boot.bin` | `0x080` | 225 | `0x70800` | 456,016 |
| `project.bin` | `0x400` | 2,798 | 5,730,304 | 5,729,640 |

The source data and the last partial page of each segment are padded with
`0xFF` exactly as in the recovery program. No bad blocks are inserted in this
first deterministic image.

## Reproducible artifact

Generated files:

- `work/emulator/h1-boot-nand.raw`;
- `work/emulator/h1-boot-nand.json`.

The manifest records the geometry, segment sources, source hashes, and output
hash. The confirmed raw-image SHA-256 is:

```text
F331FF921015C04251DF6F7C768AA2310F3A808F37613EB6425533A79CB74D44
```

Status: **confirmed**. All 3,026 programmed pages passed data and OOB/ECC
comparison in the builder's post-write verification.

## Full 512 MiB backing

The QEMU NAND model exposes ID `EC DC 10 95 44`. Device ID `0xDC` selects a
512 MiB data area: 262,144 pages or 2,048 H1 erase blocks. A 62-block file is
enough to preserve the recovery-written boot area, but it is not large enough
for normal firmware runtime because program operations beyond its end fail.

The matching full-device artifact was generated with
`--physical-blocks 0x800`:

```text
work/emulator/h1-512m-nand.raw
work/emulator/h1-512m-nand.json
raw bytes: 553,648,128
SHA-256: F416A5D33C5A1D9E5222BD106BF896F0CE8183C1AC4DDF03CADF79579913F2F2
```

The builder now hashes output files incrementally, so verifying this full
backing does not allocate a second 528 MiB memory buffer. Data and OOB/ECC for
all 3,026 boot pages passed the same post-write comparison as the compact
artifact.

Runtime status: **confirmed**. With the compact image, firmware remains in the
FTL program/retry path and eventually treats out-of-range blocks as bad. With
the full backing, it completes empty-volume initialization and reaches the
upper event and LCD drawing loop within 15 seconds, without guest errors or
unimplemented MMIO.

## Superseded empty-volume limitation

Both early artifacts lacked the normal BBK NAND FTL volume represented by the
482 files in the firmware package's `系统数据` directory. The full backing lets
the OS create an empty volume and reach its event loop, producing a 480x272
deep-blue screen with only the top-left cursor. The next step is to reconstruct
the logical filesystem and its physical page metadata, then inject those files
without changing the verified boot-area pages. That work is now complete in
`work/emulator/h1-1g-a5-system.raw`; see `08-ftl.md`. A later runtime reformat
was traced to missing NAND `05/E0` handling in QEMU and has also been fixed.
