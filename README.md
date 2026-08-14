# BBK H1 reverse engineering

This repository contains reproducible research and tooling for the BBK
`@ibox H1` learning device. The documented targets include its JZ4740-based
hardware, BDA application format, NAND/FTL layout, firmware boot path, and H1
emulation support.

Start with the [research notebook](docs/README.md) for confirmed findings,
inferences, open questions, and reproduction notes.

## Repository layout

- `docs/`: reverse-engineering notes and verified runtime observations.
- `scripts/`: firmware inspection, NAND/FTL, BDA, test, and privacy-audit tools.

Firmware, NAND images, recovery packages, ROMs, IDA databases, runtime logs,
compiler toolchains, and generated binaries are intentionally excluded. The
[open-source project split](docs/15-open-source-projects.md) explains the
separate SDK, emulator, and private game-port boundaries.

## License

Original source code and documentation are licensed under the
[Apache License 2.0](LICENSE). Screenshots and other depicted third-party
interfaces or artwork are research evidence only and are excluded from that
license as described in [NOTICE](NOTICE).
