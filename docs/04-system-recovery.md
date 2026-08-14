# System-recovery program and NAND boot layout

Last updated: 2026-07-22 (Asia/Irkutsk)

## Runtime mapping

The H1 `系统恢复.bda` header does not encode a load or entry address. The H2
reference decoder's `0x81C30040` is therefore not portable metadata.

H1's own module loader and the recovery payload's linked references establish
the following runtime layout:

- module/API table: `0x83C00000..0x83C0003F`;
- payload and entry: `0x83C00040`;
- initialized image end: `0x83C54F54`;
- BSS begins at `0x83C54F30` and extends into the `0x83D2xxxx` range.

Status: **confirmed**. At this base IDA recognizes 157 functions, 58 strings,
and 389 call-graph edges. At the copied H2 base it recognizes only 13
functions and no call edges. The entry calls, globals, API table reads, and
BSS clearing all resolve at the H1 base.

The recovery module copies five service-table pointers from
`0x83C00004..0x83C00014`. These provide the BBK OS core, GUI, filesystem,
media, and control APIs. The recovery image is an application running on top
of BBK OS services, not a standalone bootloader.

## Input files

The recovery application opens these files from the SD card:

- `B:\底层升级\loader.bin`;
- `B:\底层升级\u-boot.bin`;
- `B:\底层升级\project.bin`.

The input buffers are initialized to `0xFF` before the actual file bytes are
read, so writes after end-of-file are NAND-erased padding. The PC recovery
package decrypts to exactly the same three input binaries; see
[03-firmware.md](03-firmware.md).

## NAND geometry

The high-level write loops and the low-level JZ4740 register accesses agree
on the following geometry:

| Property | Value | Evidence |
| --- | ---: | --- |
| data bytes per page | 2,048 (`0x800`) | program/read/compare loop size |
| spare bytes per page | 64 (`0x40`) | temporary page buffer is `0x840` bytes |
| pages per erase block | 128 (`0x80`) | block number is shifted left by 7 |
| data bytes per erase block | 262,144 (`0x40000`) | 2,048 x 128 |

Status: **confirmed** for the large-page NAND path used by this recovery
image.

## Spare area and ECC

Before programming each boot-area page, the recovery code fills the complete
2,112-byte data-plus-spare buffer with `0xFF`, then clears spare offsets 2, 3,
and 4. The resulting six-byte spare prefix is therefore:

```text
FF FF 00 00 00 FF
```

JZ4740 Reed-Solomon parity starts at spare offset 6. Each 2,048-byte data page
is divided into four 512-byte chunks, with nine parity bytes generated per
chunk using the controller's RS(511,503) layout. The erased-page test vector
for one 512-byte chunk is `CD9D9058F48BFFB76F`.

Status: **confirmed** from the recovery buffer initialization and ECC-register
path. The independent encoder in `scripts/jz4740_ecc.py` reproduces the erased
chunk vector and is used by the raw NAND image builder.

The probe reads a five-byte NAND ID and contains vendor/capacity tables for
Toshiba, Samsung, Fujitsu, National, Renesas, ST Micro, and Hynix devices from
128 MiB through 2 GiB. The exact production chip ID is not present in the
archive and remains **open**; the emulator can initially expose any supported
large-page ID with sufficient capacity.

## Boot-area layout

| Physical NAND range | Blocks | Content | Recovery behavior |
| --- | ---: | --- | --- |
| `0x000000..0x03FFFF` | 0 | `loader.bin` | writes and verifies 3 pages (`0x1800` bytes), padding the 5,016-byte file with `0xFF` |
| `0x040000..0x1FFFFF` | 1..7 | `u-boot.bin` reserve | starts at block 1, skips unusable blocks, writes/verifies `0x70800` padded bytes, and must finish by block 7 |
| `0x200000..0xF7FFFF` | 8..61 | `project.bin` reserve | erases the range, skips unusable blocks, writes the runtime file length, and verifies every page |

The OS start offset `0x200000` independently matches U-Boot's own
`nand_read_skip_bad` call, which loads up to `0x600000` bytes from that offset
to `0x80004000` and jumps there. Status: **confirmed**.

The much larger physical range reserved by the recovery utility is a bad-block
budget, not the amount U-Boot copies into RAM. The H1 V1.41 `project.bin` is
5,729,640 bytes and fits U-Boot's `0x600000` read limit.

## JZ4740 NAND interface

Confirmed memory-mapped accesses include:

| Address | Observed role |
| --- | --- |
| `0xB3010050` | EMC NAND control; bit 1 enables/disables the NAND interface |
| `0xB8000000` | NAND data port |
| `0xB8008000` | NAND command port |
| `0xB8010000` | NAND address port |

The probe issues reset command `0xFF`, then ID-read command `0x90` with address
zero. Program, read, erase, spare-area, status, and read-back comparison paths
are all present. This gives the emulator a concrete MMIO contract before the
full `project.bin` peripheral survey is complete.

## IDA database

The correctly based working database is
`work/analysis/system-recovery-h1.elf.i64`. Confirmed names saved in it are:

| Address | Name |
| --- | --- |
| `0x83C00070` | `module_init_api_tables` |
| `0x83C02790` | `nand_write_verify_loader` |
| `0x83C02950` | `nand_write_verify_uboot` |
| `0x83C02B70` | `nand_write_verify_os` |
| `0x83C03730` | `nand_probe` |

Some low-level routines use shared basic blocks and multiple entry points.
They remain conservatively unnamed until their exact entry boundaries are
reconstructed; their observed MMIO behavior is still usable for emulation.
