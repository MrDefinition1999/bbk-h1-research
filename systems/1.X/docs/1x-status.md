# V1.41 focused validation

Updated: 2026-08-04

## Fixed control sequence

`scripts/h1_runtime_control.py boot-kov-page` performs the verified fixed
sequence after reset:

1. Wait for automatic four-point calibration to report complete.
2. Tap the `否` button at the changed-time prompt.
3. Tap the `确定` button at the low-space prompt.
4. Send six Page Down key presses with a settling delay; extra presses at the
   final page are ignored by the desktop.

The final page was verified by frame capture to show the `三国战纪+` icon. The
script has an optional `--launch` flag that taps that icon. It uses only the
local emulator HTTP API and never opens a browser audio stream.

## KOV dynamic result

On the reconstructed KOV NAND, the emulator reached the native 448x224 game
view, showed the opening/demo and playable scene, produced 22050 Hz PCM, and
responded to Start, direction and action events. A long Esc press returned to
the desktop. A long Back press also returns when held long enough for the slow
guest timer; the fixed automation uses Esc semantics and a two-second hold in
the game instructions.

At the final observation the QEMU process was alive, frame sequence was
advancing, audio DMA counters were advancing, and no runtime error was
reported. The emulator remained at the real H1 336 MHz baseline; no host clock
boost was enabled.

## Tests and release

- H1 SDK focused tests: 33/33 passed with the bundled Pillow dependency.
- KOV native regression tests: 11/11 passed.
- Rebuilt `H1KOVPlus.bda`: 703,812 bytes,
  SHA-256 `8526C198CF0AD1058DF9E5F745E87122E46A7291E12B58C52A83E883B4B9FD80`.
- Owner-authorized KOV package:
  `deliverables/H1-KOV-Plus-real-hardware-2026-08-04.zip`, 21,016,746 bytes,
  SHA-256
  `07D4ABE498CA59E497D55DB9D2B7D8838D28081B5D36BE548CD207025EDCB995`.

The archive contains exactly the requested `A-root` tree and
`游戏说明.txt`. Its staging tree and the ZIP itself passed
`scripts/audit_release_secrets.py` with zero findings, and 7-Zip reported
`Everything is Ok`.
