# H1 V2.x system reconstruction

Updated: 2026-08-04

## Official inputs

The H1 V2.x support listing is:

`http://app.eebbk.com/content/list?prodId=6b4e71ffed11cba87464866b9101f139&module=121&isNewEdition=1`

The two V2.20 system packages were downloaded with aria2c into the isolated
`references/official/h1-v2` research directory:

- PC super recovery executable, 462,206,976 bytes, SHA-256
  `8F4B305777C3DD36E5FB460D9CCBE5F3D397999CF832C82895F074FC8761681F`.
- SD-card one-key recovery RAR, 443,697,917 bytes, SHA-256
  `794B8D79B15847B35916CE6BB7B0D39D59F5D2D470F18D8453AC8E71EF97EB54`.

The SD RAR passed a full 7-Zip integrity test. It contains four files:

- `@ibox_H1_系统恢复程序.upd`, 834,423,583 bytes.
- `sysResume.dlx`, 1,223,924 bytes.
- `系统恢复.bda`, 52,264 bytes.
- `readme.txt`, 482 bytes.

The PC executable is a custom PE/self-extracting recovery program. Generic
7-Zip recognizes an embedded bzip2 stream at offset 52,228 and then reports a
large tail; this is a format-detection limitation, not sufficient evidence of
damage. It must be analyzed as a PE plus overlay and must not be executed just
to discover its payload.

## UPD container confirmed

The checked-in parser is `scripts/parse_h1_v2_upd.py`. It opens the UPD through
an OS mapping and copies only selected entries, so analysis does not require a
second full image. On the official V2.20 image it reports:

- table offset `0x708` (decimal 1800), record width `0x100`;
- 307 contiguous records, with GBK `A:\...` paths;
- indexed payload ending at `0x149B075A` (decimal 345,704,282);
- a 488,719,301-byte unindexed tail;
- 339,813,642 bytes extracted from the indexed records (178 DLX, 61 BDA,
  18 BIN and the documented dictionary/media resources).

The complete indexed tree is retained only under the private `work/` research
area. It is not a release input. The parser has regression coverage for the
unaligned table, GBK decoding, traversal rejection and the official 307-entry
shape.

The indexed tree contains the later V2 application layout, including
`A:\应用\数据\player.bin`, `A:\应用\数据\shell\*.dlx`, the V2 learning
content BDAs, and `A:\系统\数据\shell\*.dlx`. This is materially different
from the V1 desktop/game tree; no V1 NAND data has been overlaid onto it.

## Recovery BDA and DLX

`系统恢复.bda` is a valid V2-specific recovery application, not a V1 BDA.
Its trusted input SHA-256 is
`af860a85ca7fc459a40c36828d51e77de11cd9b674f4a4833a28ca996f1d1a8e`; the
40,228-byte payload SHA-256 is
`099b39dd2a6f4923f25d395b0f0c2af7ed37dbeabc5fd6ed467020d66b588a58`.
The payload is MIPS32 little-endian code loaded by the H1 V2 recovery loader
at `0x83C00040`. The static scanner
`scripts/analyze_h1_v2_recovery_bda.py` reports 10,057 instruction words, 262
direct `jal` instructions, 1,664 branch/control-flow instructions and the
embedded paths and diagnostics below:

- `H1\sysResume.dlx` and `H1\@ibox_H1_*.upd`;
- `nfdrv_erase_block`, `page_per_block`, `page_size`, `startBlock` and
  `endBlock` diagnostics;
- `machineid`, memory-size choices from 128 MB through 2 GB, and NAND vendor
  names;
- recovery progress/error files (`err_read*.txt`, `err_write*.txt`) and
  `resume`/`desktop` state names.

The separately shipped `sysResume.dlx` is a 14-resource variant-3 DLX package
named `Vrix 06/07/17`. All 14 resources are VX images (five 94x31/227x10/24x24
small UI assets and the 480x272 recovery backgrounds), so it is UI data rather
than executable code. The recovery logic resides in the BDA above.

## PC recovery executable

The checked-in static inventory is `scripts/analyze_h1_v2_super_recovery.py`.
The V2.20 PC package is a PE32 (`machine=0x014c`) with eight sections, image
base `0x00400000`, entry RVA `0x9978`, no certificate or relocation directory,
and 14 normal PE resources (icons, version/string data and a dialog resource).
The first framed overlay stream begins at file offset `0xCB14` (52,244); the
`BZh` member starts at `0xCB24` (52,228), decodes to 1,584,128 bytes, and has
output SHA-256
`fdd043d14eae2b7571acf4d605fe7f8e12ee0c039cc7b8d037e9d16fc2485744`.
Its output starts with `MZP`, consistent with an embedded Windows recovery
tool. The remaining overlay is deliberately not executed or unpacked in bulk.

## PC overlay members and the UPD tail

The checked-in `scripts/scan_h1_v2_super_streams.py` validates the framed BZip2
members without writing their decompressed contents. There are 24 valid
members; the other `BZh` byte sequences in a raw signature scan are false
positives or nested data. Two members are the relevant package payloads:

- member at compressed offset `5,945,383`, compressed size `111,666,783`,
  decompressed size `339,941,658`;
- member at compressed offset `117,612,170`, compressed size `343,863,738`,
  decompressed size `488,846,293`.

Both begin with a `bbk.` wrapper. The wrapper has a 16-byte header followed by
500 fixed 0x100-byte slots. A slot stores a 32-bit file size, a 32-bit payload
offset relative to the wrapper's 16-byte header, and a 248-byte tagged path
field. The header's record count is 307 for the indexed package and 268 for
the tail package. `scripts/inspect_h1_v2_bbk_wrapper.py` and
`scripts/verify_h1_v2_bbk_index.py` reproduce this layout.

For the 307-record member, all 307 slot sizes equal the SD UPD index sizes;
the offsets are contiguous, the payload sum is `339,813,642`, and the final
payload ends at wrapper offset `339,941,642` (16 bytes after the member's
payload end). The eight-character tags in the path field are not the raw
payload CRC32: a direct CRC32 comparison is 0/307, so they remain an
unidentified package tag rather than a checksum claim.

The second member is the same package format for the unindexed data. Its
wrapper payload is `488,718,277` bytes. The output suffix beginning at
decompressed offset `128,016` has the same length and SHA-256 as the SD UPD
tail beginning at UPD offset `345,705,306` (tail-relative offset `0x400`):

```text
PC suffix SHA-256  = 7c8181891ba5468078c0ee4d0e5c634ebc78f006d29676a772008b1f98910c6c
UPD tail suffix    = 7c8181891ba5468078c0ee4d0e5c634ebc78f006d29676a772008b1f98910c6c
length             = 488,718,277 bytes
```

The 1,024 bytes before the first `EEBBKBLM` marker are a separate tail prefix;
they are not included in that PC package member suffix. The marker itself is
at tail-relative offset `0x400` and appears 24 times. The markers partition
the tail into 24 blocks whose boundaries match the second wrapper's payload
record boundaries exactly; each block length equals the sum of its assigned
record sizes. Every marker has the fixed prefix `EEBBKBLM 88 95 A8 B1` and a
version word of one. Later header words split the first record's 64-byte BLM
header into two size-like fields, but their semantic names are not claimed
until the BLM payload transform is recovered.

The 1,024-byte prefix has RGB565-like values and is retained as opaque data;
it is not assumed to be a filesystem or NAND header. The full tail therefore
has a confirmed package mapping, but its BLM payload transform and its NAND
partition meaning remain open.

The indexed PC and SD payloads are not interchangeable. Their 307 record sizes,
offset order and paths match, but the first payload byte and the complete
concatenated-payload hashes differ (`scripts/compare_h1_v2_indexed_member.py`).
Runtime BDA-loader tracing and header validation establish which representation
belongs in the mounted FAT volume: all 61 PC-member BDA records pass the native
`BBK\0`, `0x5D245562`, header-checksum and payload-offset checks, while all 61
same-index SD records fail at the first check. The PC member is therefore the
authoritative final-file source for the 307 indexed records. The SD indexed
area contains recovery-transform data and must not be copied directly into a
FAT image. This distinction does not apply to the tail suffix, whose byte-level
hash equality is confirmed above.

The tail work is reproducible with:

```text
scripts/analyze_h1_v2_upd_tail.py
scripts/summarize_h1_v2_blm_headers.py
scripts/map_h1_v2_blm_blocks.py
scripts/compare_h1_v2_super_member.py
```

IDA's headless worker currently exits with code 106 for both the raw recovery
payload and a minimal ELF wrapper. That is recorded as an environment/tooling
limitation, not as a reverse-engineering result; the conservative MIPS scanner
and PE parser remain reproducible without running the firmware or updater.

## PC DAT transform and decoded boot components

The embedded PC recovery tool carries the low-level H1 images as `data0.dat`
through `data4.dat`. Their wrapper transform is now confirmed from three
complete V1 PC-DAT/SD-raw known-plaintext pairs (`loader.bin`, `u-boot.bin`
and `project.bin`):

- a 16-byte container header beginning with `26 04 04 20`;
- ciphertext beginning immediately after that header;
- a fixed 4,096-byte periodic XOR stream applied from payload offset zero;
- all bytes of all three known pairs reproduce exactly, not just their first
  block or recognizable strings;
- the derived 4,096-byte stream has SHA-256
  `A490CEA451287528E95113C57442D01409CAFAACC9DF05A67704B86A5AABE3C6`.

The reproducible decoder is `scripts/decode_bbk_pc_dat.py`. It does not embed
an unexplained vendor key: it derives the stream from a caller-supplied trusted
known pair, validates the entire pair, and only then decodes a target DAT.
`scripts/test_decode_bbk_pc_dat.py` covers the three complete V1 pairs and all
three tests pass.

Applying that confirmed transform to the V2.20 updater yields the following
private research components. These are decoded analysis inputs and are not
release artifacts:

| PC object | DFM role | Decoded size | SHA-256 |
| --- | --- | ---: | --- |
| `data0.dat` | Loader | 5,192 | `B8F5D40381672D27854FDCA5D8FE480EF6D3DA317096CFC8EE8A25B18D37F160` |
| `data1.dat` | U-Boot | 44,624 | `8577B6CAE9B90866B898FEDF3FA3ABB1FB88A2098E16A0E36E39E9BED605C8A1` |
| `data2.dat` | OS | 796,272 | `FA77B06A6C0D1679FE672FC9ABC7C3A7E4EA9374F8D5A6E6A9D2686D1891886C` |
| `data3.dat` | ExtOs1 | 3,676,424 | `BE6313C6C634E00331C463DFC12C92DEDFD43BCF173A58EF5CA4BDB062B62767` |
| `data4.dat` | ExtOs2 | 1,150,608 | `339BE4FEB60565EA475C17A2EA668C0FBC58ADE9E83380ADF6A25028EDABC57C` |

Static strings and MIPS structure distinguish the roles further. The decoded
ExtOs1 image contains the V2 desktop, DLX/resource loading, touch and main
application framework. ExtOs2 contains QC/version handling and IPMSG
(`飞鸽传书`) communication code. Two additional decoded configuration objects
are 216 and 1,053 bytes respectively (SHA-256
`FC46285FE14BC7A3FBDC4A1910A28C617C0D9EF4C448D48294FC2CC4A675CB26`
and `C40599F28371803F42EBFF0FEF05E6DDA67AAB4143B87BD545E1A5710CDA9079`)
and contain recovery path/directory configuration; their field semantics are
still being resolved.

The embedded Delphi form configuration assigns BurnSys load address
`0x80004000`, extended BurnSys address `0x82000000`, and separate filesystem
roots `Data` and `Data2`. It labels the five images as Loader, U-Boot, OS,
ExtOs1 and ExtOs2, which independently confirms the ordering above. The same
updater contains a 4,168-byte USB boot image identical byte-for-byte to V1 and
a 692,544-byte JZ4740 `BurnSys_iboxh1.bin` containing NAND, FAT, USB and file
write logic.

The binary Delphi form begins at embedded-tool file offset `0x8F014` and is a
valid 998,038-byte `TPF0` component stream. The checked-in read-only parser
`scripts/parse_delphi_binary_dfm.py` consumes the complete stream and records
large image properties only by size and SHA-256. The default H1 fields are:

| Region | Start block | Total blocks | PC file |
| --- | ---: | ---: | --- |
| Boot0 / Loader | 0 | 1 | `data0.dat` |
| U-Boot | 1 | 5 | `data1.dat` |
| OS | 6 | 10 | `data2.dat` |
| ExtOs1 | 16 | 34 | `data3.dat` |
| ExtOs2 | 50 | 12 | `data4.dat` |
| system parameters | 62 | 2 | configured by the recovery tool |

The regions are contiguous and cover logical blocks 0 through 63 without a
gap. The DFM also specifies USB bootstrap file `usb_init.bin` at target
`0x80000000`, main BurnSys at `0x80004000`, and extended BurnSys at
`0x82000000`. These values are now confirmed as updater defaults. Their unit is
named "block" by the tool, but the NAND erase-block geometry and bad-block
translation must still be confirmed in the H1 BurnSys code before constructing
a physical NAND image.

### Runtime link and ExtOs load layout

The three executable system components are not position-independent fragments.
Their startup code and exact file ends establish the following runtime layout:

| Component | Runtime base | File end / BSS start | Initial BSS end |
| --- | ---: | ---: | ---: |
| OS (`data2.dat`) | `0x80004000` | `0x800C6670` | `0x80598628` |
| ExtOs1 (`data3.dat`) | `0x80600000` | `0x80981908` | `0x809E4920` |
| ExtOs2 (`data4.dat`) | `0x809F0000` | `0x80B08E90` | `0x80B7FEB0` |

For OS and ExtOs1 the first startup basic block explicitly clears from the
exact file-end address shown above. ExtOs2 does the same after first receiving
its callback/service pointer, and subtracting its exact 1,150,608-byte size
from `0x80B08E90` gives base `0x809F0000`. Direct `j`/`jal` targets remain
inside each component (11,979 in OS, 34,853 in ExtOs1 and 14,316 in ExtOs2);
cross-component services are dispatched indirectly, consistent with the
ExtOs entry ABI rather than accidental concatenation.

OS routine `0x800507F0` constructs two NAND image descriptors. Its constant
table confirms destination addresses `0x80600000` and `0x809F0000`, ordinary
start blocks 16 and 50, and actual image read counts 15 and 5 blocks. Those
read counts equal `ceil(file_size / 0x40000)` for ExtOs1 and ExtOs2, confirming
a 256 KiB erase-block payload unit. They are the occupied image sizes, whereas
the DFM's 34- and 12-block values are reserved partition capacities. A NAND
mode flag read by the same routine selects alternate start blocks 74 and 108;
the alternate layout must not be used until that board/NAND mode is identified
from the loader and system-parameter records.

## Isolation and compatibility rules

V2.x firmware, extracted files, NAND images, emulator state and documentation
must remain separate from V1.41. V1 NAND data must never be overlaid onto V2
until the V2 filesystem and service contracts are understood.

The later game-compatibility work will compare the V1 Mission BDA imports and
runtime behavior with the V2 service table. The decision order is:

1. Run unchanged if V2 already exports the required BDA services.
2. Add an application-level compatibility shim if only service numbers or
   lightweight wrappers differ.
3. Patch the V2 system only when a required kernel/device capability is truly
   absent and cannot be supplied by a normal BDA.

No conclusion about Mission compatibility is recorded until those imports and
services have been measured.

## Reconstructed V2 NAND image

`scripts/build_h1_v2_nand.py` builds a V2-only 1 GiB NAND image from the five
decoded low-level components and the authoritative SD-UPD filesystem records.
It uses the partition map recovered from the PC updater and starts filesystem
FTL allocation at physical block 64. Blocks 62 and 63 remain erased because
their system-parameter format has not yet been recovered; no guessed parameter
record is inserted. The generated analysis image is:

```text
work/v2-emulator/h1-v2-system.raw
size:    1,107,296,256 bytes
SHA-256: B67AFE2FC8E2AB134C3E50D4DEAD3F6865BD0FCAAE6B49A0A412293DEF4D3AD4
```

The builder's independent readback pass confirms:

- all 307 indexed V2 files reproduce their source payload bytes;
- all 1,310 mapped FTL units have valid committed slots;
- no invalid or torn slot is present;
- Loader, U-Boot, OS, ExtOs1 and ExtOs2 reproduce their input bytes page by
  page, including generated ECC/OOB metadata;
- the V1 default FTL scan start remains block `0x3E`; V2 explicitly selects
  block `0x40`, so the two layouts are not silently conflated.

This establishes a byte-verified V2 NAND construction. Full BootROM execution
through Loader and U-Boot is still a separate test and is not implied by the
direct-OS boot described below.

## V2 direct-OS boot and touchscreen contract

The decoded OS runs at `0x80004000` in the H1 QEMU machine with the reconstructed
V2 NAND attached. LCD setup completes and the first-boot four-point calibration
screen is visible. Runtime inspection at the correct SADC physical address
`0x10070000` confirms the V2 driver configures:

```text
ADENA  = 0x04
ADCFG  = 0x0002504C
ADCTRL = 0x09 while released, 0x11 while pressed
ADSAME = 0x000A
ADWAIT = 0x03E8
```

Capstone disassembly of OS routines `0x8001094C` and `0x80010A2C` confirms the
register semantics rather than inferring them from V1:

- SADC interrupt number is 12 and is unmasked in the INTC;
- `ADSTATE` is write-one-to-clear;
- the driver computes pending events as `ADSTATE & ~ADCTRL`;
- event bits are `PEND=0x10`, `PENU=0x08`, `DTCH=0x04`, `DRDY=0x02`;
- every `DTCH` event consumes two 32-bit `ADTCH` words: packed X/Y followed by
  a Z sample, and five complete samples are filtered before publication.

The emulator supplies that sequence correctly. A held test touch produced five
identical X/Y/Z samples and the OS published press event `0x0B`, release event
`0x08`, X/Y coordinates at `0x80314962`/`0x80314964`, and the expected filtered
values. The original calibration timeout was therefore not an interrupt or
FIFO failure.

The actual V2 calibration routine at `0x8000D9C0` validates four raw-coordinate
ranges. Its left edge requires raw X `0x0065..0x01F3`, while its right edge
requires `0x0E11..0x0F9F`. V1 uses the opposite X direction. Reusing the V1
frontend mapping sent raw X `0x0E74` for the V2 left-top cross, so V2 correctly
rejected every otherwise valid touch. The Windows frontend now has explicit
`--touch-profile v1|v2` mappings. V1 remains the default; V2 uses its own
non-shared mapping and a bottom raw Y safely inside V2's validated range.

IDA Pro MCP is reachable, but its headless worker exits with code 106 when
opening the generated MIPS32 ELF wrapper. This is recorded as a tooling
limitation. The addresses and behavior above come from reproducible Capstone
disassembly plus live register/RAM measurements, not from a failed IDA import.

## ExtOs1 tail-block rejection

Four-point V2 calibration now completes. The following ExtOs load failure was
then reproduced with a QEMU GDB write watchpoint at virtual `0x80980818`:

- physical NAND block 30 first writes the expected ExtOs1 word
  `0x807ED15C` through OS byte-copy instruction `0x80005960`;
- the same instruction subsequently replaces it with `0x0006AC03`, exactly
  ExtOs2 file offset `0x818`;
- the second write still belongs to the first ExtOs descriptor. Its stack has
  destination-page base `0x80980800`, image base `0x80600000` and descriptor
  pointer `0x80598110`;
- the NAND block saved on the stack changes from 30 to 50. The loader rejected
  block 30, scanned the remaining reserved ExtOs1 partition, and accepted the
  first programmed page of ExtOs2 at block 50 as a replacement for ExtOs1's
  last logical block.

This rules out the earlier DMAC-alias hypothesis. Both writes are performed by
the OS NAND copy loop, and the ExtOs2 descriptor at `0x8059814C` has not started
when the corruption occurs.

The reconstructed NAND originally programmed only `ceil(file_size / 2048)`
pages. ExtOs1 therefore programmed only four pages in its final 256 KiB block;
the remaining 124 pages retained raw erased OOB bytes. A programmed all-`0xFF`
data page is not byte-identical to a raw erased page: its JZ4740 ECC OOB bytes
are non-`0xFF`. The V2 loader reads complete 256 KiB logical blocks and rejects
the raw-erased tail. `scripts/build_h1_v2_nand.py` now block-pads OS, ExtOs1 and
ExtOs2 so every page read by their descriptors has matching ECC metadata.
Loader and U-Boot retain their independently confirmed fixed write spans.

The block-padding rebuild succeeded: ExtOs1 and ExtOs2 now load at their
confirmed addresses. The next visible USB-cable prompt is also understood. OS
routine `0x806130AC` reads GPIO `PDPIN & 0x40`, which is H1 PD6 charger/cable
detection; `--no-charger` therefore produces the same prompt as disconnected
hardware and does not indicate a UDC or touch failure.

The subsequent automatic USB-recovery path is triggered by
`0x8061A424 -> 0x806192FC`. It tries to open
`A:\\系统\\数据\\shell\\DiyRes.dlx` and calls `0x8068D9B4` when the open fails.
Offline FAT traversal proves that this 390,272-byte file and every parent
directory are present in the reconstructed NAND. Live tracing narrows the
failure to the FAT lookup at `0x800268D0`, which returns `ENOENT` (`0x12`), not
to drive-letter parsing or `fopen` dispatch.

A writable runtime probe explains the discrepancy. The pristine candidate has
1,310 mappings, all at FTL sequence 1, with `应用` at cluster 2, `系统` at cluster
13,817 and `DiyRes.dlx` at cluster 14,821. During boot the guest preserves only
logical units 0 through 53, erases sequence-1 records from logical 54 onward,
and creates a minimal filesystem in new records. It writes logical units 1 and
2 at physical blocks 1,400 and 1,401 with sequence 8; the resulting guest root
instead has `系统` at cluster 2 and `应用` at cluster 6. Blocks 62 and 63 do not
change, so this is not explained by guessed or empty system-parameter contents.

The builder had two independent weaknesses exposed by this probe:

- V2 inherited the generic sequence-1 default even though the guest's current
  FTL write generation is 8.
- Offline verification silently scanned from the V1 block `0x3E` instead of
  the V2 block `0x40`, and did not reject duplicate logical mappings.

The V2 builder now has an explicit sequence override for controlled probes. The
shared FAT/FTL builder uses the caller's scan boundary during verification,
rejects duplicate logical mappings, and erases every stale mapped record rather
than only each logical unit's offline-selected record.

The clean sequence-8 rebuild is now offline-verified:

```text
work/v2-emulator/h1-v2-runtime-probe.raw
size:    1,107,296,256 bytes
SHA-256: 8F22263D70C824A3E84A10371B17FD08FD8C65F2E653AC1550D1539F42735434
```

Its manifest records 1,310 mappings, sequence 8, V2 scan start block 64,
zero duplicate logical mappings and zero bad/invalid/torn slots. Independent
readback reproduces all 307 source files. Direct FAT traversal resolves
`系统\\数据\\shell\\DiyRes.dlx` through clusters 13,817, 13,818, 13,819 and
14,821, and confirms its 390,272-byte directory size.

Runtime validation disproves the sequence-only hypothesis. After 36.8 seconds
the V2 four-point calibration completes, but the system still enters the black
USB-recovery screen with green `正在连接电脑...` text. During the run it erases
the same 1,256 physical records from block 120 onward even though their sequence
is 8, leaving only logical units 0 through 53. The writable image then has 54
selected mappings, and `系统\\数据\\shell\\DiyRes.dlx` no longer resolves.

The identical physical cutoff across sequence 1 and sequence 8 points to stale
template metadata rather than mapping generation comparison. A later BBT
inspection narrows this further: the preserved `bbt8` record has two all-`0xFF`
data pages, and the guest-created replacement is also normally all `0xFF`.
`bbt8` is handled as a separate special record at OS `0x8001F518` and
`0x8001FAB0`; it is not a logical allocation map.

The ordinary mapping scanner compares each OOB logical number against the
global at `0x80108344`. A live early-boot read gives `0x6F4` (1,780), so logical
54 is well inside the accepted range. Adjacent globals are page size `0x800`,
OOB size `0x40`, raw stride `0x840`, pages per FTL unit `0x80`, and unit size
`0x40000`, matching the reconstructed geometry. The guest therefore recognizes
the complete mapping set before a higher-level filesystem recovery/format path
deletes logical units 54 onward.

Every tested sequence-8 record on both sides of the cutoff, including logical
52, 53, 54, 55, 100 and 1,309, has all 128 pages programmed with matching OOB,
commit tails and JZ4740 ECC. Sparse-page or ECC rejection is ruled out. The
remaining leading hypothesis is that a FAT/FTL template created by V1 is not a
valid initialized volume for V2. `scripts/erase_h1_ftl_region.py` provides a
reproducible way to retain the confirmed V2 low-level blocks while presenting
an empty FTL so V2 can generate its own native template.

After that template is captured and the desktop is stable, the emulator must
pass a no-`-kernel` BootROM test through Loader -> U-Boot -> OS. Mission
compatibility will be measured only after the V2 service table is live; an
application compatibility shim remains preferable to modifying the
bottom-layer system.

## Native V2 filesystem template and first-boot configuration

V1 and V2 do not share a compatible FAT template. The V1 volume has label
`9388` and 2,001,376 sectors. A V2 guest allowed to initialize an empty FTL
creates label `Y100 V2.2` with 824,288 sectors. The captured empty V2 template
is stored as `work/v2-emulator/h1-v2-native-empty-template.tar.gz`:

```text
archive SHA-256: 27BAC4A559C17E325A9773CAF3E4D535CFFF68215E2EEB1AC49728EA8FB367ED
raw SHA-256:     7E3FE874C6221B58EC638A41938A465D7697FF1CDA324BAAB764B0E1F582A0C3
```

A writable boot from the fully populated candidate modifies only logical
units 1, 2, 3 and 1,309. It replaces the preloaded `系统` and `数据` directory
clusters, creates `Config.inf` and `SysTp.cfg`, and then cannot find the old
`系统\\数据\\shell\\DiyRes.dlx`. Two independent runs generated byte-identical
configuration files:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `Config.inf` | 1,332 | `06D353A111BC7C2AD6DAF9AC46391DC6525B8C3A0215899CF008AD0B67C11FA1` |
| `SysTp.cfg` | 76 | `99A247782271425A437F7138D31EC70410E0FBE9FCAA422188046CD255DF02D6` |

The repeated output proves these are deterministic firmware defaults in the
emulated H1 environment, rather than host paths or random memory. `Config.inf`
contains the GBK string `雷霆战机`; its field meaning is not yet assigned.
The binary files remain unedited. `scripts/stage_h1_v2_native_config.py`
verifies their fixed sizes and hashes before atomically staging them under
`work/v2-indexed/系统/数据`. A mismatch is fatal unless an explicit `--force`
replacement is requested.

The first rebuild with those files still entered USB recovery. The writable
probe preserved all 1,310 original mappings and added only four duplicate
logical records plus one BBT, so the native V2 geometry had already fixed the
earlier mass deletion. The guest nevertheless replaced both root directories;
the new `系统/数据` contained the same two configuration hashes and no `shell`.

The native template contains two generations of logical units 0 through 3.
The generic sequence comparison selected an empty-root logical 3 whose root
volume-label entry is `@ibox H1`. The coherent guest-initialized logical 3 is
physical block 146, sequence 0. It contains root label `H1`, `系统` at cluster 2,
`数据` at cluster 3, `Config.inf` and `SysTp.cfg` at clusters 4 and 5, and `应用`
at cluster 6. Its FAT copies are the sequence-8 records in physical blocks 144
and 145. The guest booted from this unchanged template without rewriting it,
confirming that the lower numeric logical-3 sequence is not stale in this
case.

The reconstructed candidate had copied the wrong `@ibox H1` root label even
though its BPB label correctly remained `Y100 V2.2`. The V2 builder now passes
the exact guest-generated 32-byte `H1` root volume-label entry through a
validated `--root-volume-label-entry-hex` option. This keeps the override
explicit and V2-specific instead of changing V1 behavior or guessing a global
FTL generation rule.

The label-only candidate still entered recovery. The remaining mismatch is
the physical record selected for logical unit 3. The generic comparator chose
the old empty-root record at block 1,783 and erased the initialized record at
block 146. The guest's newer BBT belongs with block 146 even though that
record's sequence field is numerically 0. `build_h1_system_nand.py` now accepts
a validated `--mapping-override LOGICAL=BLOCK[:SLOT]`; it refuses an override
unless exactly one committed record has the requested logical and physical
identity. The V2 wrapper first requires native-template SHA-256
`7E3FE874C6221B58EC638A41938A465D7697FF1CDA324BAAB764B0E1F582A0C3`, then
selects `3=146:0`. No override is applied to V1 or to an unknown V2 template.

## Indexed filesystem source correction

The first native-layout candidate reached the main framework but reported that
`A:\应用\程序\中学时间.bda` was missing or had an incorrect version. A GDB
breakpoint at the ExtOs1 BDA-loader entry `0x806173F4` confirmed that exact path.
The file staged from the SD UPD began with help text instead of an encrypted BDA
header, although NAND readback reproduced the staged bytes exactly. The failure
was therefore above FTL/FAT construction.

`scripts/validate_h1_v2_bda_sources.py` streams the 339,941,658-byte PC updater
member at compressed offset 5,945,383 without materializing it. It retains only
the BDA headers and validates both sources against the loader contract:

```text
SD indexed records:  0 / 61 valid BDA files
PC wrapper records: 61 / 61 valid BDA files
PC compressed size: 111,666,783 bytes
PC output size:     339,941,658 bytes
```

The machine-readable result is `work/v2-bda-source-validation.json`. This
invalidates the earlier `work/v2-indexed` filesystem source even though its
307 payloads were copied without byte errors. The next candidate must be built
from a separately extracted PC-member tree, followed by the two verified native
configuration files; the SD-derived tree is retained only as transform-analysis
evidence and is not overwritten.

`scripts/extract_h1_v2_pc_member.py` now performs that extraction in one BZip2
stream. It checks the wrapper/UPD record count, every size, contiguous payload
boundaries, duplicate host paths and all 61 BDA headers before atomically
committing `work/v2-pc-indexed`. Its manifest records 307 files and a member
output size of 339,941,658 bytes with no trailing data. The two deterministic
native configuration files increase the build input to 309 source files.

The V2 NAND builder now rejects a filesystem tree unless it contains exactly
61 valid BDA files. This makes accidental reuse of the SD recovery-transform
tree fail before a 1 GiB output is allocated. The corrected candidate is:

```text
work/v2-emulator/h1-v2-runtime-probe.raw
size:    1,107,296,256 bytes
SHA-256: 8283D51E341B3552FC4EC9BDBBD57640AA4D01C86B46C616F587FFD709A59151
```

Its complete build/readback verification reports 1,310 mappings, zero duplicate
mappings, one BBT, zero invalid/torn slots, 310 verified FAT file extents and
340,625,878 verified bytes. `DiyRes.dlx` reads back with SHA-256
`5E174E577E42887DD509F660824E3F1941DB5D57091D4C43A096458ACFEB1B9A`.

Direct-OS snapshot boot with the V2 touch profile now loads
`A:\应用\程序\中学时间.bda` and displays its complete clock/date interface; the
version-error dialog is gone. Hardware Return reaches the full V2 subject
desktop. Touch opens the English application, opens its top-bar help at display
coordinate `(430,10)`, and closes the help page at `(452,8)`. The visible
top-bar icons have narrower application hit regions than their artwork, but the
SADC, affine calibration and application touch dispatch are live. Captured
evidence is stored as `v2-pc-source-boot.png`, `v2-pc-source-after-back.png`,
`v2-touch-english.png` and `v2-touch-grid.png` under `work/v2-emulator`.

## Complete NAND boot chain

The Windows frontend now has an explicit `--bootrom` mode. It omits `-kernel`
and enables the machine's NAND BootROM path while retaining snapshot, input and
frame streaming. The first probe exposed a frontend address mismatch: the
BootROM copied the 6,144-byte Loader to the direct-OS address `0x4000`, where
offset zero is `0xFFFFFFFF`; the CPU remained at `0x80004000` with repeated
reserved-instruction exceptions.

The Loader stub is linked for physical address zero: its first executable word
is at offset four and its startup jump targets `0x80001018`. BootROM mode now
sets `firmware-phys=0` and `reset-pc=0x80000004`; direct `-kernel` mode keeps the
OS load address `0x4000`. The corrected runtime reports:

```text
kernel:       null
bootrom_nand: true
BootROM:      6144 bytes, NAND normal address 0x00000000
load address: physical 0x00000000
reset PC:     0x80000004
```

From that state the NAND Loader and U-Boot reach the corrected V2 OS and load
the same complete Time application. Hardware Return reaches the subject desktop
and touch opens the English application. The snapshot remained live for more
than 153 seconds with advancing guest instructions, live frames and no runtime
error. Evidence is `v2-bootrom-chain.png`, `v2-bootrom-desktop.png` and
`v2-bootrom-touch2.png` under `work/v2-emulator`.

## V1 Mission compatibility baseline

The unmodified V1 `mission-original.bda` has SHA-256
`7729907A10511CAA54C3E286DDE91B9D3F18940C6F51034D1088350261AED8C4`, a
payload offset of `0x785C`, and executes at the normal H1 application address
`0x83C00020`. Static service-call tracking finds 70 distinct table-relative
offsets in the application.

V2 native applications use three executable payload offsets: `0xF04` in 37
files, `0x2F04` in 23 files, and `0x3524` in one file. The existing scanner's
core recognizes their calls; its old command-line filter admitted only V1's
`0x785C` layout and therefore incorrectly reported zero V2 applications. The
new `scripts/compare_h1_v1_v2_service_calls.py` scans both layouts without
changing the V1 inventory tool's established behavior. Reproducible results
are stored in `work/v2-mission-service-compat.json` and `.md`.

Across all 61 V2 BDAs, 333 distinct service offsets are observed. Only 24 of
Mission's 70 offsets occur in a native V2 application. Of the 46 unobserved
offsets, 45 are high GUI-table slots from `+0x2B8` and `+0x84C..+0xADC`; the
remaining offset is `RES+0x094`. Mission's FS, SYS, and ordinary resource
dependencies otherwise have native V2 call-site evidence. This pattern is
consistent with V2 removing or replacing V1's game graphics/resource extension
layer rather than replacing the complete BDA ABI. Static slot overlap does not
yet prove identical signatures or semantics; runtime table and entry probes are
required before a compatibility shim is selected.

Dynamic GDB-RSP inspection of the running V2 Time application establishes a
second ABI difference. V2 installs a 64-byte prefix at `0x83C00000` and places
application code at `0x83C00040`; V1 normal applications have a 32-byte prefix
and code at `0x83C00020`. The V2 prefix words are:

```text
00000000 80790BA0 800A50A0 800A4FD0
800A5554 80AE55C0 800A5144 00000000
00000000 00000000 8008A9A4 8008AAEC
80AE5460 807D89C0 00000000 00000000
```

The first five table slots retain the V1 GUI/FS/SYS/MEM/RES positions, but V2
adds live values beyond byte `0x20`. Running V1 confirms its original prefix is
only the first eight words and its normal code address is `0x83C00020`.

`scripts/probe_h1_service_tables.py` checked all 70 Mission offsets against the
stopped V2 guest. Sixty-six entries are non-null pointers into the V2 OS,
ExtOs1 or ExtOs2 executable ranges. Four genuine V1 GUI services are absent:

| Slot | V1 pointer | V2 contents |
| ---: | ---: | --- |
| `GUI+0xAA4` | `0x8004550C` | `0x20202020` (text data) |
| `GUI+0xAA8` | `0x80045850` | `0xFAD6EFB0` (text data) |
| `GUI+0xAD8` | `0x80066FA8` | `0x2D2D2D2D` (separator text) |
| `GUI+0xADC` | `0x8006703C` | `0x2D2D2D2D` (separator text) |

Mission has real `jalr` call sites for every one of these slots, so they are
not linear-disassembly false positives. The remaining compatibility work must
therefore handle both the `0x20` load-address delta and these four removed
services. Merely changing the BDA header or category cannot make the original
binary safe on V2.

The SDK builder now accepts an explicit `entry_va`/`--entry-va` while retaining
`0x83C00020` as the V1 default. Nine standard-library build tests pass,
including an ELF entry-point assertion for V2 address `0x83C00040`.

A minimal dialog probe linked at `0x83C00040` was packed with the existing H1
`0x785C` resource envelope and substituted for `中学时间.bda` in an isolated
copy of the V2 NAND. The V2 loader accepts this envelope and hits the probe's
entry at exactly `0x83C00040`; header bytes and decoded header fields are also
visible on the loader stack. This proves a new V2-specific icon envelope is not
required merely to execute an SDK application.

The same probe calls the V1 message-box slot `GUI+0x2B8`. A breakpoint confirms
the V2 function receives the expected `(0, message, title, 0)` arguments, but it
returns immediately without drawing a dialog. Therefore a non-null V2 table
entry, even one located in executable memory, does not prove V1-compatible
semantics. The 66 executable Mission slots require semantic mapping; only the
24 offsets independently called by native V2 BDAs currently have static ABI
continuity evidence, and even those still need signature-level confirmation.

Probe deployment no longer requires another full NAND build. The structured
`scripts/replace_h1_fat_file_in_nand.py` reuses an existing FAT cluster chain,
updates the directory size, rewrites only affected logical FTL units with fresh
JZ4740 ECC/OOB, and validates FAT readback and mapping count. Replacing the
120,264-byte Time BDA with the 30,964-byte probe touched logical units 709, 711
and 712 (384 pages); all 1,310 mappings remained present and readback matched
SHA-256 `DE5682F5375E2446AAED6D58697391FF0BBDCF6E60C6B4E8B8A71F1EFE93D6B7`.

## Native B volume and playable Mission result

IDA analysis closes the earlier storage-model gap. The V2 Resource Manager root
always inserts `[B:]`, conditionally inserts `[C:]`, and intentionally omits A.
Its directory walker appends `\\*.*` and calls the V2 find-first, find-next and
find-close services. The OS path parser maps A/B/C to volume indices 0/1/2.

The NAND FTL scanner has two hard physical windows at 256 KiB per block:

- A: blocks 120 through 1779 (30 MiB through 445 MiB);
- B: blocks 1780 through 4095 (445 MiB through the 1 GiB device end).

The retained native V2 image contains 1,310 A mappings ending at block 1434 and
no mapped or BBT record in the B window. The blank B view is therefore original
behavior, not a failure to expose A. The superseded expanded build allocated A
records beyond block 1780 and also retained V1 FAT geometry; those records
crossed the V2 partition boundary.

A writable cold boot created a native empty B volume with four logical mappings
and one BBT record. Its FAT16 geometry is label `Y100 V2.2`, boot LBA 32, 512
bytes per sector, 32 sectors per cluster, 480 reserved sectors, two FATs, 512
root entries, 512 sectors per FAT and 1,149,920 total sectors.

`h1_ftl.py`, `build_h1_system_nand.py` and the in-place FAT replacer now accept
an exclusive scan-end block. This prevents A allocation or verification from
crossing `0x6F4`. `merge_h1_v2_b_volume.py` byte-verifies that the boot/A prefix
comes from the selected base and the B suffix comes from the separately built
volume. A NumPy batch ECC path reproduces the scalar JZ4740 parity while reducing
the 77,312-page B build to seconds; the scalar implementation remains the
dependency-free fallback.

The B filesystem contains the trusted V1 files at
`B:\应用\数据\游戏\LYXZ`:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `DataLib.dat` | 157,063,229 | `4E67278C6E5EED5E650E470E788D8BF0C7DE9436F07815AF2DA7A35EEFBC3DE5` |
| `DataLibIndex.dat` | 180,216 | `7852C4199EA2B7A6D1990DE540844FFDA6A24D2930D6EDF79C477146582A2F79` |

`patch_h1_v2_mission_resource_drive.py` requires exactly five occurrences of
the Mission-private `A:\应用\数据\游戏\` prefix and changes only each drive
letter to B. It rejects an unexpected count and proves that no other byte
changed. This leaves all V2 system paths and all unrelated BDA paths on A.

`navigate_h1_v2_mission.py` attaches to an already healthy cold boot by default
and navigates without taking or matching screenshots; a restart is available
only through explicit `--reset`. It clears the boot prompts, exits the restored
native application and category with two hardware Return events, taps inside
Tools/Entertainment at `(462,251)`, sends Page Up to select its first page, and
selects the native Time slot at `(153,207)`. That slot loads the verified
external Mission wrapper because it replaces `中学时间.bda`.

The earlier `(438,251)` category coordinate was on a boundary and the earlier
`(402,61)` target could launch an unrelated English BDA. After correcting both,
a live run reached the Mission main menu with advancing guest instructions and
no QEMU error. The script now reports only `mission-launch-inputs-sent`; final
screen identity remains an explicit terminal check. On 2026-08-18 the user also
manually confirmed that this first Mission entry enters the game and is
playable. The old `V1Loop` entry reported missing data and the embedded
experiment hung; both were removed by restoring their native V2 BDAs.

One redundant BootROM restart stopped in a repeated exception loop at PC
`0x81002834` while the retained frame still said `请重新设置时间！`. Input events
were accepted by the backend but could not be consumed by the guest, proving
that Return/Confirm mapping was not the cause. A complete frontend/QEMU restart
restored advancing instructions before navigation continued.

The cleaned private image is:

```text
work/v2-emulator/h1-v2-mission-b.raw
size:    1,107,296,256 bytes
SHA-256: 529D02B39AD015B1B846C5F83B20ABF6F45B49590B771ED6C32E6994D46E512C
```

## Mission movement cadence A/B

A coordinated 1.X/2.X map-movement comparison on 2026-08-18 kept both H1
instances at the same 64 MiB, 336 MHz guest clock, single-thread TCG and 17 ms
LCD refresh settings. It did not enable instruction-clock acceleration, MTTCG,
extra RAM or any other performance option. The sampler read `/api/status` only;
it did not capture screenshots, inject input or change emulator state.

After the operator's click was visible in the frame sequence, V1 advanced 260
changed frames in 13.30 seconds (19.55 changed frames/s). Its one-second guest
instruction intervals remained between approximately 4.4 and 10.3 million
instructions/s. The equivalent V2 Mission interval advanced 98 changed frames
in 14.82 seconds (6.61 changed frames/s). During the visible pauses, one V2
interval advanced only 3,206 guest instructions in about 1.27 seconds; the next
several intervals remained in the tens or hundreds of thousands while AIC DMA
completions continued to advance.

Both instances use the host bridge's same 1,000 ms performance packet. V1 did
not exhibit the V2 instruction-rate collapse, so that packet and a browser-only
paint delay are excluded as the cause of this observation. The confirmed fault
domain is the V1 Mission-on-V2 application/service compatibility path: the
guest's Mission main path stops doing useful work while emulated audio hardware
continues. This does not yet identify the individual service. Investigation
should next trace the V1 `GUI+0x84C..0x9F8` event, wait and drawing calls against
their relocated V2 implementations; changing CPU/RAM/TCG settings would hide
rather than diagnose the defect.

`scripts/sample_h1_mission_cadence.py` makes the status-only measurement
repeatable. Run it separately against ports 8793 and 8796, click a distant map
point when it prints `CLICK_NOW`, and retain only the small JSON reports:

```powershell
python scripts/sample_h1_mission_cadence.py --base-url http://127.0.0.1:8793 --output work/mission-cadence-v1.json
python scripts/sample_h1_mission_cadence.py --base-url http://127.0.0.1:8796 --output work/mission-cadence-v2.json
```
