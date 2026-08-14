# Open-source project split

The 12+ GiB research workspace is not a publishable Git repository. Most of
its size is firmware, raw NAND images, recovery packages, toolchains, private
game data, generated analysis output, or local public-reference checkouts.
Those inputs remain local and are never GitHub release contents.

## Repository plan

| Repository | Purpose | Upstream/license boundary | Initial status |
| --- | --- | --- | --- |
| `bbk-h1-research` | Confirmed H1 reverse-engineering notes and reproducible NAND, FTL, UPD, firmware-inspection, deployment, and privacy-audit scripts. | Original source and documentation use Apache-2.0; depicted third-party interfaces and artwork are excluded by `NOTICE`. | Ready after fixture sanitization and archive audit. |
| `bbk-h1-bda-sdk` | Freestanding MIPS BDA compiler, packer, verified H1 API headers, examples, probes, and tests. | Independent H1 implementation under Apache-2.0; verification screenshots retain their original rights. | Ready without `ports/kov_pgm`. |
| `bbk-h1-emulator` | H1 board and JZ4740 device support layered on the existing `HelloClyde/bbk9588-emulator` QEMU overlay. | Preserve upstream Git history and GPL-2.0-compatible licensing by using a GitHub fork. No firmware or NAND image is included. | Publish as a fork after applying and testing the H1 patch set. |
| `bbk-h1-kov-port` | Source-only KOV/PGM runtime, renderer, audio, profiling, and tests. | Never include ROM, BIOS, PAK, runtime logs, or built BDA files. The reviewed `fba-a320` A68K/CZ80 and PGM-derived source has no repository-wide license, so provenance must be resolved before public release. | Local Git only until the license review is complete. |

Future V2 game probes belong in the SDK until they become a reusable project;
an experiment with no stable public API should not create another repository.

## Material that must stay local

- Vendor RAR/EXE/UPD recovery packages and extracted firmware trees.
- Raw NAND images, overlays, checkpoints, BootROM, U-Boot, OS, and recovery
  binaries.
- ROM, BIOS, PAK, WAD, game archives, and built proprietary payloads.
- IDA databases and unpacked database side files.
- Compilers, Python runtimes, QEMU binaries, caches, virtual environments, and
  third-party Git checkouts.
- Unreviewed screenshots, logs, deployment reports, local absolute paths,
  usernames, hostnames, credentials, and tokens. The four reviewed A320
  behavior captures under `docs/assets/` are documentation evidence covered
  by the repository `NOTICE`, not Apache-2.0 assets.

## Publication gate

For every repository and release archive:

1. Rebuild from tracked source without local absolute paths.
2. Run the relevant unit and integration tests.
3. Run `python scripts/audit_release_secrets.py <stage-or-repository>`.
4. Build an archive from tracked files and audit the archive itself.
5. Verify the archive contains no prohibited binary or private-data suffix.
6. Push only after all findings are zero.
