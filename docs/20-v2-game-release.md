# V2 game compatibility release

Updated: 2026-08-24

## Release boundary

The publishable deliverable is a reproducible, source-only project. It contains
the compatibility-stage source, NAND installers, verification tests and these
path records. It intentionally excludes vendor firmware, NAND images, original
BDA files, game payloads, game resources, AVI files, IDA databases and generated
binaries. A user must supply lawfully obtained V1/V2 inputs locally.

The final V2 NAND layout keeps launchers and executable payloads on the hidden
system volume A, where the V2 BDA loader already expects them. Every packaged
game data/resource file is on the Resource Manager-visible B volume. Moving the
large data to B avoids crossing V2's fixed A/B FTL boundary and does not require
a risky global OS path patch.

## Complete guest paths

The Mission icon uses the native Time application's filesystem slot. Its BDA
header/title is Mission, but the final launcher filename remains
`A:\应用\程序\中学时间.bda`. This distinction matters when inspecting or
rebuilding the NAND.

| Game | Launcher on A | Executable payload on A | Resources/data on B |
| --- | --- | --- | --- |
| 使命 | `A:\应用\程序\中学时间.bda` | `A:\V1GAME.BIN` | `B:\应用\数据\游戏\LYXZ\DataLib.dat`; `B:\应用\数据\游戏\LYXZ\DataLibIndex.dat` |
| 中国象棋 | `A:\应用\程序\中国象棋.bda` | `A:\CHESS1.BIN` | `B:\应用\数据\游戏\cheRes.lib`; `B:\应用\数据\游戏\CheSnd.lib` |
| 俄罗斯 | `A:\应用\程序\俄罗斯.bda` | `A:\TETRIS.BIN` | `B:\应用\数据\游戏\els.lib`; `B:\应用\数据\游戏\elssound.lib` |
| 宠物泡泡 | `A:\应用\程序\宠物泡泡.bda` | `A:\PETPOP.BIN` | `B:\应用\数据\游戏\popo.lib`; `B:\应用\数据\游戏\posnd.lib`; runtime save `B:\应用\数据\游戏\user.bin` |
| 猫狗大战 | `A:\应用\程序\猫狗大战.bda` | `A:\CATDOG.BIN` | `B:\应用\数据\游戏\dvc.lib`; `B:\应用\数据\游戏\dvcsnd.lib` |
| 雷霆战机 | `A:\应用\程序\雷霆战机.bda` | `A:\FLYJET.BIN` | `B:\应用\数据\游戏\flydata.lib`; `B:\应用\数据\游戏\flydata1.lib`; `B:\应用\数据\游戏\flydata2.lib`; `B:\应用\数据\游戏\flydata3.lib`; `B:\应用\数据\游戏\flydata4.lib`; `B:\应用\数据\游戏\FlySound.lib` |
| 黑白子 | `A:\应用\程序\黑白子.bda` | `A:\BWGAME.BIN` | `B:\应用\数据\游戏\black.lib`; `B:\应用\数据\游戏\blacksound.lib` |

FAT16 lookup is case-insensitive. The original 俄罗斯 and 黑白子 payload strings
spell `elsSound.lib` and `blackSound.lib`; they resolve to the lowercase
directory-entry spellings shown above.

## Checked drive rewrites

`install_h1_v2_v1_game_suite.py` does not perform a broad byte replacement.
For each external payload it requires an exact number of
`A:\应用\数据\游戏\` strings, changes only the one-byte drive letter, proves
that the payload length is unchanged, and rejects any residual A game-data
root.

| Game | Payload offsets changed to B | Count |
| --- | --- | ---: |
| 中国象棋 | `0x126D0`, `0x126F0` | 2 |
| 俄罗斯 | `0x51F0` | 1 |
| 宠物泡泡 | `0x16440`, `0x17010`, `0x17058` | 3 |
| 猫狗大战 | `0xDCA0`, `0xDCEC` | 2 |
| 雷霆战机 | `0x1BD9C` | 1 |
| 黑白子 | `0x9E6C` | 1 |

Mission uses the separate checked patcher and requires exactly five
Mission-private roots. System and unrelated application paths stay on A.

## Reproduction and verification

Starting from the verified Mission+B image, the six-game installer uses two
independent physical windows:

- A: `[0x40,0x6F4)` for six launchers and six executable payloads;
- B: `[0x6F4,0x1000)` for all sixteen packaged resource files.

The A phase proves that B is unchanged. The B phase proves that the entire
boot/A byte range is unchanged. Both phases reopen their FAT volumes and compare
every installed file byte-for-byte.

```powershell
python tooling/install_h1_v2_v1_game_suite.py `
  --template .local/derived/h1-v2-mission-b.raw `
  --v1-image .local/inputs/h1-v1-system.raw `
  --wrapper-template .local/derived/mission-stage-arena.bda `
  --output .local/build/h1-v2-v1-games-b.raw `
  --manifest .local/build/h1-v2-v1-games-b.json `
  --python-ecc
```

The private verification build was 1,107,296,256 bytes with SHA-256
`7CDBA2CA81CB3E252752C39F70642FBA8648AB8CBC3F2409B241BF3C1EA0D031`.
Its A region SHA-256 was
`E37A4C6EAF5A80056C113D6612F003F7918AE8063FE0793A3F8606569BA0E108`;
its B region SHA-256 was
`E7C1275FD4BFAF705C2539BFB0606C755474A7B77D5BA0CA43F4E3652AF0A56A`.
A gained two mapped logical units and retained 4,737 free FAT clusters. B
gained 167 mapped logical units and retained 23,602 free FAT clusters.

The six source games use 106 unique service slots and have zero statically
unmapped calls. Unit tests cover wrapper specialization, exact drive-byte
rewrites and unexpected-path-count rejection. Mission is user-verified playable.
The other six games have complete static coverage and byte-level installation
verification, but gameplay, audio, save and normal-exit behavior remain pending
manual validation; the release makes no stronger claim.

## Lessons for continued work

- Do not enlarge A beyond physical block `0x6F4`; V2 scans the remainder as B.
- A blank B in an original V2 image is expected: the factory image has no B
  mappings, and the guest creates its native empty volume.
- Keep compatibility at application level. A global A-to-B OS patch caused a
  black screen.
- Reuse the verified stage-arena wrapper only after its SHA-256 and every
  expected instruction sequence match. Do not use the earlier trace build whose
  marker overlapped compatibility memory.
- Treat static ABI coverage and FAT readback as necessary, not as a gameplay
  result. Record manual validation per game.
- Keep all proprietary/generated inputs under ignored local directories. Build
  a Git archive from tracked files and audit the archive itself before release.
