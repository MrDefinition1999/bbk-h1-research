# Reference projects

Last updated: 2026-07-23 (Asia/Irkutsk)

## H1 public product and hands-on evidence

Product page supplied by the user:
<https://baike.baidu.com/item/%E6%AD%A5%E6%AD%A5%E9%AB%98%E8%A7%86%E9%A2%91%E5%AD%A6%E4%B9%A0%E6%9C%BA/861476>

The direct page currently presents an anti-crawl challenge in the automated
browser. The user supplied the two relevant specifications from that page:

- internal flash: 1 GB, with approximately 500 MB occupied by the system;
- expansion: Micro SD/TF, up to 16 GB.

Independent H1 V1.41 hands-on article:
<https://post.smzdm.com/p/a2x9le02/>

The article was inspected directly. It describes a working 1.41 machine as a
2008 model with a 4.3-inch 480x272 display, 1 GB internal storage, Micro SD/TF,
a resistive touchscreen, and a slide-out full keyboard. It also records that
1.41 retains games while later 2.1 firmware removes them; keyboard-only control
is incomplete and normal operation requires the touchscreen; there are no
dedicated volume buttons. The article photographs are **not** treated as
evidence for the default power-on screen or exact UI state because no verified
default-boot sequence is shown. Emulator framebuffer states that need visual
identification will be presented to the user in a local HTML review surface.

The two sources agree on 1 GB internal storage. Together with the guest-created
`0xD3` geometry and recovery payload size, this closes the production-capacity
question at 1 GiB. The article is a user hands-on report rather than a teardown,
so it does not identify the NAND chip marking.

## H2 research article

Source: <https://zhiyb.github.io/blog/2026/05/23/Reverse-engineering-BBK-ibox-H2/>

The article was inspected directly. Its H2 workflow covers:

1. recovery package inventory and SoC identification;
2. UPX removal and Windows recovery-program analysis;
3. USB first-stage and second-stage loader analysis;
4. encrypted data-file recovery;
5. kernel, interrupt, MMC, filesystem, BDA, and main-program analysis;
6. QEMU/GDB iteration and device-specific sanity checks.

The article contains two GitHub project links that must be reviewed:

- <https://github.com/OpenNoah/bootrom>
- <https://github.com/zhiyb/eebbk_tools>

The article-resource audit was repeated on 2026-07-23. The rendered article
contains 26 image assets; all 26 loaded successfully with non-zero natural
dimensions and were inspected in article order. They cover the UPX-packed
Windows recovery executable, USB loader disassembly, GDB/character-set work,
touch calibration, FAT16 boot records and headers, the first desktop and
settings screens, recovery/update failures and success, RTC and hardware
revision checks, SD/eMMC behavior, and the serial-number/AES investigation.
The article element contains 82 link elements when its date, section anchors,
image links, tags, and previous-article navigation are included. Only two of
those links point directly to GitHub repositories: `OpenNoah/bootrom` and
`zhiyb/eebbk_tools`. Both repositories were reviewed at the pinned commits
recorded below, rather than merely noting their landing pages.

H2 screenshots are method and failure-state references only. They must not be
used to identify H1's default power-on UI; that requires an H1 emulator
framebuffer capture and, where ambiguous, local HTML review by the user.

Important H2 facts are not yet H1 facts. In particular, the article identifies
H2 as JZ4750L-like hardware and derives an AES key from MMC CID bytes; both are
only candidate patterns until independently confirmed in H1 binaries.

## 9588 emulator

Source: <https://github.com/HelloClyde/bbk9588-emulator>

Reviewed at commit `b398bc527b207957259405b19a60771fe34d4fc0`. Its QEMU
11 overlay implements a dedicated JZ4740/XBurstR1 CPU and board models for CPM,
INTC, TCU, GPIO, SADC, MSC, LCD, DMAC, AIC, UDC, EMC/ECC, RTC, and raw NAND.
This is the primary emulation base candidate for H1, subject to board-level
address, IRQ, LCD, input, and NAND-layout differences.

## IDA Pro MCP

Source: <https://github.com/mrexodia/ida-pro-mcp>

Reviewed at commit `120ae7abd871bd32d6002d5f9c4233a26ecdfd65`. Upstream
recommends the headless `idalib-mcp` supervisor for Codex and retains the GUI
plugin for interactive/debugger use. Results are in [02-ida-mcp.md](02-ida-mcp.md).

## H2 scripts and boot ROM

- `zhiyb/eebbk_tools` commit
  `98171b616613072e03315f7693b38ba2093700d9` supplies the H2 image/BDA/SN
  scripts. The BDA algorithm is public domain and is confirmed compatible with
  H1.
- `OpenNoah/bootrom` commit
  `2759ce0020c3e823384d82af34741f93ebfbe46e` contains QEMU boot ROM code and
  linker layouts for JZ4740, JZ4750, JZ4750L, and JZ4755. It is a candidate for
  the reset/boot-ROM stage rather than an H1-specific result.
