# Reproducible BBK H1 2.X project

This is the source-only reproduction entry point for BBK `@ibox H1` 2.X. It pins the public SDK and emulator revisions, records SHA-256 identities for official V2.20 inputs and derived components, and includes the V2 NAND reconstruction plus V1-game ABI compatibility tooling. Vendor packages, NAND images, BDAs, game data, and generated binaries never enter Git.

```powershell
python .\scripts\bootstrap_components.py
python .\scripts\verify_inputs.py
python .\scripts\verify_source_project.py
```

Place your lawful V2.20 PC and SD recovery packages in `.local/inputs/`. See [reproduction](docs/reproduce.md), [complete seven-game paths and release verification](docs/game-release.md), [2.X status](docs/2x-status.md), and [V1 game compatibility status](docs/v1-game-compat-status.md). The final layout keeps only launchers/executable payloads on hidden A; all game resources are on Resource Manager-visible B.

Original project code and documentation use Apache-2.0; the fetched emulator retains GPL/QEMU upstream terms.

中文: [README.md](README.md)
