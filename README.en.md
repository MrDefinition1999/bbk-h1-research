# BBK H1 reverse engineering

This repository contains reproducible research and tools for the BBK `@ibox H1`
learning device. The scope covers its JZ4740/XBurst hardware, BDA application
format, NAND/FTL layout, firmware boot path, and H1 emulator validation.

Start with the [research notebook](docs/README.md), which separates confirmed
facts, inferences, open questions, and reproduction steps.

## Repository boundary

- `docs/`: reverse-engineering findings, verification records, and methodology.
- `scripts/`: firmware, NAND/FTL, BDA, test, and privacy-audit tooling.
- The SDK, emulator, and KOV game port are maintained as separate projects; see
  [the project split](docs/15-open-source-projects.md).

Firmware, NAND images, recovery packages, ROMs, IDA databases, runtime logs,
toolchains, and generated binaries are excluded. The KOV PGM port and real-device
test package remain private research artifacts.

中文入口: [README.md](README.md)

## License

Original source code and documentation are licensed under the [Apache License
2.0](LICENSE). Screenshots and depicted third-party interfaces or artwork are
research evidence only; see [NOTICE](NOTICE).
