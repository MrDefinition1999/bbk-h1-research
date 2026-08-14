# H1 NAND FTL and FAT volume

## 2026-08-04 template recovery (confirmed)

The guest-created A5 template was regenerated from an erased NAND seed by the
official V1.41 `project.bin`, then the reserved `0x3e` boot blocks were restored
from the rebuilt boot NAND. The resulting 1 GiB image is:

```text
work/emulator/h1-1g-a5-template.raw
bytes: 1107296256
SHA-256: 61D5E7FC87E4C635407977BA4B0E1768F1EEF442BFB5DA84BA27E090F2281203
```

Runtime scan and full OOB/ECC inspection match the historical guest evidence:
four mappings at physical blocks `0x41..0x44`, BBT at `0x45`, sequence `1` for
all mappings, BBT sequence `2`, and logical-unit SHA-256 values
`82185C64...`, `A68EA6C1...`, `A68EA6C1...`, `BAC919B2...`. The firmware reached
all four touch-calibration points on both a stock NAND and the KOV-injected NAND
under x86-64 QEMU with snapshot mode enabled.

The old synthetic template (`5B678854...`) is a rejected failure artifact. The
recovery is reproducible with `scripts/build_h1_empty_template.py` using
`--format-seed`, the official guest formatter, and `--overlay-boot`.

Last updated: 2026-07-23 (Asia/Irkutsk)

## Active evidence

The active template is `work/emulator/h1-1g-a5-template.raw`. It is a 1 GiB
raw NAND image initialized by the original H1 V1.41 firmware while QEMU
reported NAND ID `EC D3 10 A5 44`:

```text
raw bytes: 1,107,296,256
physical blocks: 4,096
post-initialization SHA-256:
61D5E7FC87E4C635407977BA4B0E1768F1EEF442BFB5DA84BA27E090F2281203
scan report: work/analysis/h1-1g-a5-template-ftl.json
```

The scan finds 4 mapped units, 1 BBT unit, 4,029 free blocks, and no bad,
invalid, or torn records.

## Corrected geometry

H1 uses one FTL mapping unit per physical erase block:

| Layer | Size |
| --- | ---: |
| NAND page | 2,048 data + 64 OOB bytes |
| physical erase block | 128 pages / 256 KiB logical data |
| FTL mapping unit | 128 pages / 256 KiB / `slot=0` |

The decisive evidence is consistent across firmware and runtime behavior:

- NAND geometry parser `sub_8004B0A0` decodes extended ID byte `0x95` as a
  128 KiB/64-page block and `0xA5` as a 256 KiB/128-page block.
- Recovery and runtime erase routine `sub_80048474` shift the block number by
  7, so both erase exactly 128 pages.
- With `0xA5`, the guest writes one mapping record per physical block and its
  four initial logical units are `0,1,2,3`.

The earlier two-independent-64-page-slot interpretation is **withdrawn**.
Those observations were produced while QEMU returned the inconsistent ID
`EC D3 10 95 44` but still erased 128 pages at a time. That mismatch allowed
two records to appear in one physical block; garbage collection of either
record erased both. It explains why a 7,196-record injected image collapsed to
127 mappings after boot.

The following images are retained only as failure evidence and must not be
used as production templates:

```text
work/emulator/h1-1g-runtime1.raw
work/emulator/h1-1g-system.raw
work/emulator/h1-1g-system-qemu.raw
```

The old complete image hash
`EE1608FB61C18708E99C5C4580C4DDBCF167F64BD32EC8EB057D35AB2EAC266F`
therefore proves only that the old 64-page writer was self-consistent, not that
the firmware could mount it safely.

## Guest-created allocation

The corrected empty-volume allocation is:

| Physical block | Slot | Kind | Logical unit | Last valid page |
| ---: | ---: | --- | ---: | ---: |
| `0x41` | 0 | mapped | 1 | 60 |
| `0x42` | 0 | mapped | 2 | 60 |
| `0x43` | 0 | mapped | 3 | 7 |
| `0x44` | 0 | mapped | 0 | 8 |
| `0x45` | 0 | BBT (`bbt8`) | - | 1 |

The scan starts at physical block `0x3E`; boot blocks below it are outside the
normal FTL window. The `slot` field remains in JSON for compatibility with old
reports, but it is always zero for the corrected H1 geometry.

## OOB commit format

For each programmed logical page:

- OOB byte 0 remains `0xFF`;
- byte 1 is cleared to mark the page valid;
- bytes 2..3 contain the highest valid page index in the 128-page unit;
- JZ4740 RS parity begins at byte 4;
- bytes 58..59 contain a 16-bit circular generation counter;
- bytes 60..63 contain `0xFFFF0000 | logical_unit` for normal mappings.

The first and last-valid page carry identical six-byte commit tails. A mismatch
is a torn update. Physical bad-block status is checked at OOB byte 0 of page
127. These rules are confirmed by the guest-created A5 image.

## Guest-created FAT16 geometry

The original firmware creates this BPB at logical LBA `0x20`:

| Field | Value |
| --- | ---: |
| boot LBA | 32 |
| bytes per sector | 512 |
| sectors per cluster | 32 (16 KiB) |
| reserved sectors | 480 |
| FAT copies | 2 |
| root entries | 512 |
| sectors per FAT | 512 |
| hidden sectors | 1 |
| total sectors | 2,001,376 |
| volume label | `9388` |
| filesystem type | `FAT16` |

Logical unit 0 holds the MBR and boot sector, units 1 and 2 hold the two FAT
copies, and unit 3 holds the fixed root directory. Unprogrammed logical pages
read as zero through the FTL even though physical NAND data remains erased.

## Tooling

`scripts/h1_ftl.py` now scans one 128-page record per block, validates the
first/last commit tails, resolves the newest generation, parses the FAT BPB,
and can extract the zero-filled logical volume. `scripts/h1_fat16.py` and
`scripts/build_h1_system_nand.py` stream 256 KiB logical units and erase/write
one complete physical block per mapping. Their old 128 KiB assumptions were
removed on 2026-07-23.

The first corrected build exposed a host-side pipe deadlock: sending all 128
pages to the native ECC helper in one write allowed its result pipe to fill
while the parent was still writing input. The writer now caps native ECC work
at 64 pages per transaction. This is an implementation limit of the Windows
pipe protocol, not an H1 NAND geometry change.

Native ECC acceleration is provided by `scripts/jz4740_ecc_native.c`. The
x86-64 Windows helper is `work/tools/jz4740-ecc-x86_64.exe`, SHA-256
`CD260962D997659D4554DEFD4A9A4DEB81EC3E9A4468B921A4D18F62CD42749B`.
It matches the Python implementation on zero-filled, erased, and random pages.

## Production capacity

The SD recovery tree contains 482 files in 51 directories, totaling
941,372,606 source bytes. The guest-created FAT16 volume has 2,001,376 sectors
from LBA 32 and fits that tree after cluster and directory overhead. This is
consistent with the user-supplied product specification: 1 GB internal flash,
approximately 500 MB occupied by the system, and up to 16 GB Micro SD/TF.

The corrected geometry has 4,034 usable scan-window blocks, of which 1 is the
guest BBT block. The planned system data consumes about 3,600 mapped 256 KiB
units, leaving several hundred blocks for free-space and FTL recycling.

## Corrected complete system NAND

The A5 streaming build completed after the ECC pipe fix:

```text
output: work/emulator/h1-1g-a5-system.raw
raw bytes: 1,107,296,256
SHA-256: E39D703FECECA817E8D48F769A38391FFB5F7887C5C11811BE0DD5071668E90C
manifest: work/analysis/h1-1g-a5-system-manifest.json
mapped logical units: 3,607
programmed pages: 456,732
global free blocks: 426
BBT blocks: 1
invalid/torn records: 0
```

All 537 planned extents were read back through the corrected H1 FTL mapping.
This includes all 482 source files; every file byte and SHA-256 matched the SD
recovery tree. Verification covered 942,201,758 bytes including FAT, directory,
MBR, and boot-sector metadata. Status: **confirmed**.

The complete system volume is structurally and operationally verified. It has
booted with the fixed NAND model, completed touch calibration, and displayed
the themed H1 desktop from the injected files. Snapshot mode preserved the
base image hash. The remaining persistence item is a no-input cold boot using
a small overlay rather than another 1.1 GB writable copy.

## Full OOB field verification

`scripts/inspect_h1_ftl_record.py` now validates every OOB field on all 128
pages of a selected mapping record. The comparison report is:

```text
work/analysis/h1-a5-ftl-record-comparison-v2.json
```

Logical units 0 through 3 were checked in both the guest-created A5 template
and the synthesized system volume. Every programmed page has the expected
`0xFF` bad-block byte, zero valid marker, record-wide `last_valid` value,
JZ4740 RS parity, all-`0xFF` 18-byte reserved area, and matching six-byte
generation/logical commit tail. Every unprogrammed page retains an all-`0xFF`
OOB. All seven mismatch lists are empty for every record. Status:
**OOB/ECC incompatibility is ruled out**.

The remaining structural difference is logical-unit continuity. The current
system image maps 3,607 units from logical 0 through 3,612, with six all-zero
holes at logical units 2,123, 2,134, 2,162, 2,173, 2,179, and 2,184. The guest
empty volume maps a contiguous 0..3 range. A new opt-in builder mode,
`--map-zero-units-through-used`, maps those zero units without changing the
default writer; its boot result will decide whether H1 requires a contiguous
mapping table through the highest used unit.

The contiguous experiment produced
`work/emulator/h1-1g-a5-system-contiguous.raw`, SHA-256
`3E7A5FE02C1389F7E51790352892061EAD8038F7608F55930A87F5C844D8D8AA`.
It contains exactly 3,613 mappings for logical units 0..3,612, no holes, 420
free blocks, and no invalid/torn records; all 482 source files still passed
FTL read-back verification. A writable copy was then booted for 20 seconds
with USB power detection disabled. The first calibration cross was visible,
but the guest had already replaced the volume with four new mappings for
logical units 0..3 and a new BBT record:

```text
runtime image: work/emulator/h1-1g-a5-system-contiguous-run1.raw
scan report: work/analysis/h1-1g-a5-system-contiguous-run1-after20s-ftl.json
```

Status: **logical-unit continuity is ruled out as the reformat trigger**. The
next control uses the same FAT/FTL writer with a single sentinel file and a
large free-block reserve, separating general FAT construction from payload
size/content and FTL reserve thresholds.

## First writable A5 boot

The first writable copy completed all four calibration points, but it did not
preserve the injected volume. Before boot it contained 3,607 mappings; after a
clean QEMU monitor shutdown it contained only the four guest-created FAT
metadata mappings plus one BBT record:

```text
post-calibration image: work/emulator/h1-1g-a5-system-run1.raw
post-calibration SHA-256:
74BBB33FF575109C4B7793E8181613E686888E8FCB48DE2628F55257D2669A5C
scan report: work/analysis/h1-1g-a5-system-run1-after-cal-ftl.json
mapped logical units: 4 (0, 1, 2, 3)
invalid/torn records: 0
```

This is a deliberate guest reformat, not the old paired-slot erase failure.
The corrected `0xA5` geometry is internally consistent, but the guest still
rejects some part of the synthesized FAT/FTL volume during mount. The next
diagnostic compares guest-created and synthesized OOB/ECC, generation counters,
and FAT metadata before changing the writer.

The preceding interpretation is retained as experiment history but has now
been superseded: the guest did perform a format, but the trigger was an
emulator NAND read-command omission rather than a FAT/FTL incompatibility.

## Reformat root cause: NAND random data output

A control reboot used the A5 template created by the original guest itself,
which removes the host FAT/FTL writer from the experiment. Before reboot its
active records were:

```text
logical 1 -> physical block 0x41
logical 2 -> physical block 0x42
logical 3 -> physical block 0x43
logical 0 -> physical block 0x44
BBT       -> physical block 0x45
```

After 20 seconds with the old QEMU NAND model, all five records had been
recreated at blocks `0x46..0x4A`. The two scan reports are:

```text
work/analysis/h1-1g-a5-template-before-reboot-ftl.json
work/analysis/h1-1g-a5-template-reboot1-after20s-ftl.json
```

Status: **confirmed that the old emulator reformatted a guest-native volume**.
This rules out synthesized directory layout, payload size, free-block reserve,
logical-unit holes, and host OOB generation as the common trigger.

IDA decompilation of the physical-page reader `sub_80047310` identifies the
missing NAND protocol operation. H1 reads a page in two phases:

1. issue `00`, column `0x0800`, row address, then `30`, and read 64 OOB bytes;
2. issue `05`, column `0x0000`, then `E0`, retaining the same row;
3. DMA four 512-byte chunks from the data area.

Commands `05/E0` are NAND Random Data Output. The old model neither reset the
column address latch for `05` nor acted on `E0`; its read cursor therefore
continued after OOB instead of returning to column zero of the current page.
The exported sector buffer was all `0xFF`. `sub_80055DDC` then rejected the
missing FAT jump/signature and returned `-2`; startup function `sub_80115510`
handles that state by calling the formatter and attempting the mount again.
The relevant IDA evidence is retained in:

```text
work/analysis/ida-decompile-80047310.json
work/analysis/ida-decompile-80049d20.json
work/analysis/ida-decompile-80049a30.json
work/analysis/ida-decompile-8004a4cc.json
work/analysis/ida-callgraph-80049a30.json
work/analysis/ida-decompile-80055ddc.json
work/analysis/ida-analyze-80115510.json
```

The QEMU NAND model now resets the address latch on `05`, preserves the
previously selected row, and reloads that page at the new two-byte column when
it receives `E0`. After this change the same guest-native template was booted
writable for 12 seconds. Logical unit 0 remained at block `0x44`, sequence 1,
and the BBT remained at block `0x45`, sequence 2. Logical units 1, 3, and 2
moved to blocks `0x4C`, `0x4D`, and `0x4E` through normal FAT activity; unlike
the old run, the volume identity was not rebuilt.

```text
fixed scan: work/analysis/h1-1g-a5-template-fixed-run1-after12s-ftl.json
old read buffer: work/analysis/h1-template-lba0-buffer-2s.bin
fixed read buffer: work/analysis/h1-template-fixed-lba0-buffer-2s.bin
fixed mount globals: work/analysis/h1-template-fixed-fs-globals-2s.bin
```

The 1.1 GB writable control copy was deleted after the scan report was written.
Status: **NAND Random Data Output handling is the confirmed reformat root cause,
and the fix is confirmed by a writable FTL preservation control**.
