# BBK H1 reverse engineering

This repository contains reproducible research and tooling for the BBK
`@ibox H1` learning device: JZ4740/XBurst hardware, the BDA application format,
NAND/FTL, firmware boot, the H1 emulator, and the boundary between 1.X and 2.X.

## System projects

- [`systems/1.X`](systems/1.X): independent 1.X reproduction entry point,
  official-input hashes, and current validation status.
- [`systems/2.X`](systems/2.X): independent 2.X reproduction entry point,
  V2 NAND reconstruction, and V1-game compatibility research.

These directories are published separately as
[`bbk-h1-1x`](https://github.com/MrDefinition1999/bbk-h1-1x) and
[`bbk-h1-2x`](https://github.com/MrDefinition1999/bbk-h1-2x).
They contain source, documentation, input hashes, and pinned public components;
vendor firmware, NAND images, commercial games, IDA databases, and generated
binaries never enter Git.

## Repository boundary

- `docs/`: confirmed results, validation records, open questions, and live state.
- `scripts/`: firmware, NAND/FTL, BDA, emulator, publication, and privacy tools.
- `systems/`: the two small version-specific source projects.

The public SDK and emulator remain in
[`bbk-h1-bda-sdk`](https://github.com/MrDefinition1999/bbk-h1-bda-sdk) and
[`bbk-h1-emulator`](https://github.com/MrDefinition1999/bbk-h1-emulator).
See [the open-source structure](docs/15-open-source-projects.md).

Original source and documentation use the [Apache License 2.0](LICENSE).
Third-party interface and artwork boundaries are documented in [NOTICE](NOTICE).

中文: [README.md](README.md)
