# H1 V1.41 Flying Video 2.X compatibility port

## Result

The H1 2.X Flying Video decryption path is byte-for-byte compatible with the
open H2 implementation for the analyzed player build.  Both use the
`EEBBKBMD` container, a `0x220`-byte encrypted header, the same 128-byte key
weights, the same embedded `0x4000`-byte XOR table and the same key-derivation
loop.  Test decryption produced identical bytes.

The complete H1 2.X player payload is now repacked for the V1.41 application
loader.  It is not a reimplementation of the container or codec.  The 2.X
player, its embedded MPEG-4/MP3 code and its original UI resource are retained;
the compatibility layer supplies the V1.41 service tables and entry ABI.

The port is deliberately restricted to the verified V1.41 firmware and these
analyzed inputs:

| Input | SHA-256 |
| --- | --- |
| V1.41 stock `飞天影音.bda` | `B964EB9CA0EF7172933D079E7209B7AE6E69CC4CD29C675814FCF348EA1853D0` |
| H1 2.X `飞天影音.bda` | `8ADFCF4981CA8ABDCA00854EF3CC499C2033976A96BC66717E18DC0A566D7043` |
| V1.41 `player.bin` | `4D51625BCAAF7F71B071212EEFB095EE9EAC7C2F2CD0DCA37226ADD74B623504` |
| H1 2.X `player.bin` | `FAB2F3CF69C449167FD7C5C933E6418AC78738720EDC749FEA3AA919A775E0E8` |

The reproducible compatibility BDA is 3,442,856 bytes with SHA-256
`753ED2D6EFF71BC51714C11A37EF34AEA1CB8DFBF225497B17835D76C86484A0`.
The builders reject any other input hashes rather than applying firmware
addresses to an unknown release.

## Loader and service compatibility

V1.41 enters a normal BDA at `0x83C00020`; the position-dependent 2.X payload
expects `0x83C00040`.  The repacker inserts a 32-byte entry prefix, keeps the
2.X payload at its original virtual addresses and places the compatibility
tables above it at `0x83F40000`:

| Range | Purpose |
| --- | --- |
| `0x83F40000` | V1-backed GUI table |
| `0x83F40B00` | V1-backed media/audio table |
| `0x83F40C00` | general-service table |
| `0x83F40F00` | extended-service table |
| `0x83F41000` | entry and framebuffer helpers |

Moved GUI and media slots were matched to V1.41 implementations in IDA.  The
general table includes filesystem-adjacent OS helpers, timing/cache services
and a live LCD framebuffer getter.  The three 2.X-only audio queue helpers have
no V1 table entry; V1's PCM write service already starts its DMA queue, so the
compatibility table supplies conservative zero-return stubs for them.

## Skin and resource files

There are no additional external 2.X skin files in this player build.  The
complete skin/UI resource is the analyzed 2.X `player.bin`.  To avoid breaking
V1 applications that share the stock resource, the installer:

- preserves `A:\应用\数据\player.bin` unchanged;
- installs the 2.X resource as `A:\应用\数据\play2.bin`;
- redirects the transplanted player to `play2.bin` and `play2.cfg` with
  size-preserving string patches;
- redirects the 2.X media root from `B:\多媒体\飞天影音\` to the V1-visible
  `A:\飞天影音\`.

The BDA still uses the stock V1.41 envelope and menu metadata, while all
in-player controls come from the exact 2.X resource.  This arrangement avoids
mixing incompatible resource indices between the two releases.

## Reproduction and NAND installation

Build the BDA from the exact extracted inputs:

```powershell
python scripts/build_h1_v1_flying_video_compat.py `
  --stock-v1-bda <v1-flying-video.bda> `
  --v2-bda <v2-flying-video.bda> `
  --v1-os-elf <v1-project.elf> `
  --output work/analysis/v1-v2-flying-video-compat.bda `
  --report work/analysis/v1-v2-flying-video-compat.json
```

Create a copied NAND image; the source image is never edited:

```powershell
python scripts/install_h1_v1_flying_video_compat.py `
  --stock-nand <stock-v1.41.raw> `
  --output <v1.41-flying-video-2x.raw> `
  --compat-bda work/analysis/v1-v2-flying-video-compat.bda `
  --v2-resource <v2-player.bin> `
  --python-ecc `
  --report <install-report.json>
```

An optional `--sample <encrypted.avi>` installs an `EEBBKBMD` sample as
`A:\飞天影音\测试.avi`.  Every replaced or added file is reopened through the
H1 FAT/FTL reader and compared byte-for-byte.  The installer also verifies
that the stock V1 resource remained unchanged.

## Dynamic validation

The transplanted player has been exercised in the H1 V1.41 emulator with the
real 64 MiB memory layout and single-thread TCG:

- a stock DX50/MPEG-4 AVI opened, produced 44.1 kHz audio, rendered a frame
  after seeking to 00:29 and returned to the desktop normally;
- the original 32,587,009-byte H2 `EEBBKBMD` sample was recognized as 13:29,
  decrypted its MP3 audio at 44.1 kHz and rendered its 480x270 FMP4 video after
  seeking to 02:10;
- the encrypted frame programmed the IPU as 480x270 YUV420 input to RGB888
  output, and displayed the expected classroom/electrolysis scene;
- seeking no longer corrupts the player, and the close path returns to the V1
  desktop.

Both ordinary and encrypted files can remain black at 00:00 for a long
decode/pre-roll interval under the emulator.  A seek to a nonzero timestamp is
the reliable validation point; black at the initial timestamp alone is not a
decryption failure.

Physical H1 hardware playback remains a separate acceptance test.  The NAND
installer intentionally creates a new image so that hardware validation can be
performed without modifying the only stock backup.

## Emulator diagnostic overlap

The former emulator diagnostic base `0x83E00000` overlaps the native 2.X
player, whose image extends through the `0x83EFxxxx` range.  A host input event
there wrote `EVENT_SCRATCH_MAGIC` over live MIPS instructions and caused a
coprocessor-unusable exception during seeking.  The QEMU overlay now reserves
diagnostics at `0x83F80000`, above the verified compatibility image end
`0x83F41070` and within the final 512 KiB of guest RAM.

`scripts/patch_h1_emulator_diag_base.py` is a fail-closed transformer for the
one verified local x86-64 test executable.  It exists only to validate this
source change when the matching QEMU build tree is unavailable.  Release
binaries must be rebuilt from the changed QEMU overlay; the transformed test
executable is not a release artifact.
