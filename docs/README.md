# H1 reverse engineering notebook

This documentation is updated as each item is verified. Statements are marked
as **confirmed**, **inferred**, or **open** so that observations from H1 are not
accidentally mixed with assumptions copied from H2 or 9588.

## Documents

- [00-inventory.md](00-inventory.md): source firmware and host tool inventory.
- [01-references.md](01-references.md): reusable findings from H2 and 9588.
- [02-ida-mcp.md](02-ida-mcp.md): IDA Pro MCP installation and validation.
- [03-firmware.md](03-firmware.md): archive, BDA, MIPS, and SoC findings.
- [04-system-recovery.md](04-system-recovery.md): recovery runtime and the
  confirmed NAND boot-area layout.
- [06-emulator.md](06-emulator.md): H1 QEMU machine implementation, build,
  and runtime milestones.
- [07-nand-image.md](07-nand-image.md): reproducible raw NAND boot image,
  OOB/ECC encoding, and current FTL boundary.
- [08-ftl.md](08-ftl.md): guest-generated H1 FTL tags, corrected 128-page geometry,
  and FAT16 volume parameters.
- [09-storage.md](09-storage.md): workspace size audit, cleanup record, and
  large-artifact retention rules.
- [10-dingoo-a320.md](10-dingoo-a320.md): official A320 V1.22 firmware,
  software-rendered 3D architecture, reproduced `7 Days` baseline, and the H1
  compatibility-port boundary.
- [11-release-privacy.md](11-release-privacy.md): permanent release privacy
  policy, path-independent builds, and archive-content auditing.
- [12-cs15-lite.md](12-cs15-lite.md): licensed-source boundary, reproducible
  9588 baseline, H1/JZ4740 platform adaptation, and performance acceptance.
- [13-kov-pgm.md](13-kov-pgm.md): user-owned V119 ROM boundary, Dingoo A320
  PGM baseline, H1 memory feasibility, and the game-specific port plan.
- [14-rebuild-status.md](14-rebuild-status.md): post-incident source recovery,
  verified toolchains, regression results, and remaining trusted-input gates.

## Current phase

The workspace has been reconstructed after an earlier storage incident. Treat
`14-rebuild-status.md` as the authority for file integrity; historical runtime
claims below are context, not proof that a corresponding local binary still
exists or remains usable.

Firmware extraction and boot-chain analysis are in progress. JZ4740, BDA
format compatibility, the recovery-module runtime base, and the NAND boot
area through `project.bin` are confirmed. The BBK OS load address, C startup,
UART, 480x272 panel, MSC, AIC, SADC, SPI, NAND, and UDC register contracts are
now documented. Filesystem partitions, exact key wiring, and the remaining
board-level peripheral details remain in progress. The first `bbkh1` QEMU
machine overlay boots `project.bin`; DMA-to-NAND and NAND aperture decoding are
implemented, and the first verified raw boot-area NAND image is ready for
runtime validation. Writable MTD runs have captured the guest-created H1 FTL
and empty FAT16 volumes for both diagnostic 512 MiB and production 1 GiB NAND.
The 1 GiB `0xD3` geometry is confirmed to fit the complete recovery tree;
The old 64-page/two-slot FTL interpretation has been withdrawn: the firmware
requires NAND extended ID `0xA5`, a 128-page erase block, and one 256 KiB FTL
mapping unit per physical block. The corrected complete volume has been built
and all 482 files have passed FTL readback verification. The repeated reformat
was traced to missing NAND `05/E0` Random Data Output support in the emulator,
not to the synthesized FAT/FTL volume. The fix is present in both ARM64 and
x86-64 QEMU builds and has preserved logical unit 0 and the BBT in a writable
guest-native control. The complete fixed system volume now boots through all
four calibration points and displays the themed H1 application desktop; the
captured framebuffer contains 5,533 colors and no network image was used for
identification. Exiting the original first-use guide, preserving calibration
with a compact overlay, both desktop wallpaper restore paths, JZ4740 IPU video
playback, and application-edge touch coordinates are now dynamically verified.
The final x86-64 delivery build has completed the same browser-driven desktop,
help, file-picker, and full advertisement AVI regression under Windows-on-Arm.
Exact key-matrix wiring and the remaining board-level peripheral details remain
the active reverse-engineering items.

The final emulator target is Windows x86-64 for Intel/AMD PCs. The ARM64 QEMU
binary is a development-host validation aid only; the packaged x86-64 binary
is the tested delivery artifact.
