# H1 firmware format and boot artifacts

Last updated: 2026-07-22 (Asia/Irkutsk)

## SD recovery archive

Extraction with 7-Zip 24.09 succeeds without errors and produces 486 files
totalling 947,911,338 bytes. The important boot/recovery files are:

| File | Size | SHA-256 |
| --- | ---: | --- |
| `loader.bin` | 5,016 | `A0EAC632582D673E7A6C2982F725429D1D8C678360FE012BE07703199376BBAC` |
| `u-boot.bin` | 456,016 | `B050643A39318479D05F27EB874FD1ECE6BD841310EA6CD93446C98120296129` |
| `project.bin` | 5,729,640 | `D05786E442F9AAD62A8D0A0CB4F6D786BDC7C2FA353A7A2B152C9ED9F01B40EF` |
| `系统恢复.bda` | 348,060 | `5208089DB885ED69D6BCB26AC6A2D32D3003A56FE24F3FBE1DC94912B092742F` |

The first instructions in all three `.bin` files decode as little-endian
MIPS32 instructions. `project.bin` contains the symbol-like ASCII string
`jz4740_spi_init` at byte offset 3,763,409 (`0x396CD1`). This is direct H1
firmware evidence for a JZ4740 SoC. Status: **confirmed**.

`u-boot.bin` contains operational strings including `Start Run U-boot In
c_main`, `Load OS image from NAND into RAM`, `SDRAMTEST SUCCESS!`, and NAND
identifiers `NAND01G-B`/`NAND02G-B`. `project.bin` contains `BBKUSB  BBK-OS
-NAND   0100`. Status: **confirmed**.

## BDA executable format

The H2 public-domain decoder was tested against H1 `系统恢复.bda` and all
sanity checks passed. H1 therefore uses the same observed BDA envelope:

- bytes `0x00..0x2B` are XOR-obfuscated by repeating ASCII `DWRD`;
- decoded magic is `BBK\0`;
- decoded marker at `0x04` is `0x5D245562`;
- the stored header checksum at `0x84` is XOR-obfuscated by `KF-2`;
- payload offset is a little-endian field at `0x14` (H1 value `0x88`);
- the header contains no load or entry address field;
- H1's module loader and the payload's linked absolute references place the
  module base at `0x83C00000` and its payload/entry at `0x83C00040`.

The last point is device-specific. The H2 reference decoder's comment uses
`0x81C30040`, but carrying that constant into H1 produces unresolved calls and
an impossible BSS range. With `0x83C00040`, direct calls, global addresses,
and the module API table at `0x83C00000..0x83C0003F` all resolve coherently.

The extracted H1 system-recovery payload is 347,924 bytes with SHA-256
`A2355342DF09ACC01DB2BD1B19528F2FF92DF49EDBD43A0FEDAFD7BBBB242C44`.
The repeatable implementation is [`../scripts/decode_bda.py`](../scripts/decode_bda.py).
Its default `0x83C00040` address describes the system-recovery ABI only. Normal
applications loaded by `project.bin` may have a shorter API prefix; pass the
observed runtime address with `--load-address` instead of treating the default
as BDA file metadata.

## PC recovery archive

The outer RAR contains a single 467,351,076-byte Windows recovery executable.
It is an Inno Setup 5.2.3 installer. `innoextract` 1.9 extracted it without
errors to `work/pc-installer/`. Its hardware-facing components are:

| File | Size | SHA-256 |
| --- | ---: | --- |
| `super_recover.exe` | 1,240,064 | `7EF39AA7AF151529D50E407D1645AE17806EEA9226647AD047049196C5B7E88B` |
| `usb_init_64M.bin` | 4,168 | `89F1DBA8140FB1BC4F44EA2E47BAB8900ACAE3587FCD139BBE7330F24F56C09A` |
| `SuperOs_Y100_V1.41.bin` | 651,760 | `B69BE25A0FBBE5715F9137B097FEB7BD38DF0E448F5AC175542A7485217D1136` |
| `data0.dat` | 5,032 | `FD2713687D942B9E1CA3724DE97108E7FFD77110567B564A5AACD72B76A35B83` |
| `data1.dat` | 456,032 | `31ABAF689345CC095D361D05FA26DFBCFE20835E985CD1363CB1144CD07A1D23` |
| `data2.dat` | 5,729,656 | `564A093F92A8D718B2AEFD14BBADB13F91DF9AB98FF81103687C3418F9DEE05F` |
| `packet1.dat` | 941,500,622 | `CF6DDE26218BCDE3A057C4839835259106B231E8CCE1478A3EBAE37F3C2574BB` |
| `alldir1.dat` | 940 | `552E362F329FF6E579478DA6F7BE6FFFCFACF9ABB73D3E3A9B9AAE8BD066CAFF` |

The installer also supplies an old Jungo WinDriver 9.01 stack and separate
USB-boot/recovery INF files. `super_recover.exe` identifies its form as
`TForm4740SysTool`; embedded defaults name `data0.dat`, `data1.dat`,
`data2.dat`, `packet1.dat`, `alldir1.dat`, a burn-code entry at `0x80004000`,
and the device label `@ibox H1`.

### Encrypted low-level images

Each `data[0-2].dat` consists of a 16-byte little-endian header followed by a
payload XORed with a repeating 4,096-byte key. The key is embedded at file
offset `0x49E60` in `SuperOs_Y100_V1.41.bin`. Decryption produces an exact
byte-for-byte match as follows:

| PC file | SD file | Match |
| --- | --- | --- |
| `data0.dat` | `loader.bin` | exact |
| `data1.dat` | `u-boot.bin` | exact |
| `data2.dat` | `project.bin` | exact |

This was checked over the complete payloads, not inferred from sizes or a
prefix. The resulting SHA-256 values are the SD-image hashes listed above.

### `packet1.dat`

The H1 packet uses the same container structure observed by `eebbk_tools` for
H2: a 16-byte global header, followed by fixed 0x100-byte entries and payloads
addressed relative to the end of the global header. Confirmed H1 values are:

- magic `0x2E6B6262` (the bytes `bbk.`);
- 482 file entries;
- index end `0x1E210` and first payload at absolute file offset `0x1F410`;
- every payload is in bounds and payload ranges do not overlap;
- all 482 paths are GBK-encoded and all 482 payloads exactly match the 482
  files under the SD package's `系统数据` directory.

Each descriptor starts with two space-separated fields before the relative
path. The second field looks checksum-like but does not equal standard IEEE
CRC-32 for any of the 482 payloads, so its precise semantics remain open.
`alldir1.dat` uses the same 16-byte/XOR envelope and decodes to 51 required
`A:\\...` directories.

The early `inspect_pc_payload.py` prototype was not retained. The maintained
V2 indexed-member extractor is
[`../scripts/extract_h1_v2_pc_member.py`](../scripts/extract_h1_v2_pc_member.py),
with the authoritative reconstruction and verification workflow recorded in
[`16-v2-system.md`](16-v2-system.md). The historical machine-readable result
was generated as `work/analysis/pc-payload-report.json` and remains a private
research artifact rather than a source dependency.

## Address hypotheses to validate

- `u-boot.bin` is loaded at cached address `0x81000000`.
- `project.bin` is loaded from NAND to `0x80004000` and entered there.

Both are now **confirmed** from U-Boot control flow.

## Confirmed U-Boot startup path

Wrapping `u-boot.bin` in a minimal little-endian MIPS32 ELF container allowed
IDA 9.3 to analyze 425 functions and 190 strings. The internal addresses align
exactly with a `0x81000000` image base:

1. entry `0x81000000` initializes CP0 and cache state;
2. BSS `0x8106F550..0x812CC200` is cleared;
3. `$gp` is set to `0x81077540` and `$sp` to `0x81256A00`;
4. control transfers to `c_main` at `0x81002FD4`;
5. `load_os_from_nand_and_jump` at `0x81003A60` selects 512- or 2048-byte
   NAND page geometry from the device ID;
6. `nand_read_skip_bad` at `0x810037F8` reads `0x00600000` bytes from NAND
   byte offset `0x00200000` to RAM `0x80004000`, rewinding the destination when
   it encounters a bad block;
7. U-Boot jumps through `0x80004000`, the BBK OS entry.

The working database is `work/analysis/u-boot.elf.i64`. Confirmed function
names and boot parameters have been written into that IDB. The source wrapper
is [`../scripts/wrap_raw_mips_elf.py`](../scripts/wrap_raw_mips_elf.py).
