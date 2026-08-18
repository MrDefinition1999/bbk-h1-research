# Reproducible BBK H1 1.X project

This is the source-only reproduction entry point for BBK `@ibox H1` 1.X. It pins the public SDK and emulator revisions, records SHA-256 identities for lawful user-supplied inputs, and carries the NAND/FAT/FTL, BDA, and emulator tooling needed to repeat the research. Vendor firmware, NAND images, commercial games, and generated binaries never enter Git.

```powershell
python .\scripts\bootstrap_components.py
python .\scripts\verify_inputs.py
python .\scripts\verify_source_project.py
```

Place your two lawful V1.41 recovery packages in `.local/inputs/`; exact names and hashes are in `inputs.lock.json`. See [reproduction](docs/reproduce.md) and [current status](docs/1x-status.md).

KOV/PGM ROMs, PAK files, and port sources with unresolved provenance are excluded. Original project code and documentation use Apache-2.0; the fetched emulator retains GPL/QEMU upstream terms.

中文: [README.md](README.md)
