# 1.X reproduction

## Requirements

- Windows PowerShell, Git, Python 3.10+, and 7-Zip.
- A MIPS little-endian toolchain for SDK applications; the SDK documentation records the tested setup.
- The two lawful V1.41 recovery packages listed in `inputs.lock.json`.

## Procedure

1. Run `python scripts/bootstrap_components.py` to fetch the exact SDK and emulator revisions.
2. Put the official archives in `.local/inputs/` and run `python scripts/verify_inputs.py`.
3. Extract the archives under `.local/extracted/`. Do not commit the result.
4. Prepare the verified V1 template as `.local/derived/h1-v1-template.raw` and the decoded OS as `.local/derived/project.bin`; their expected hashes are recorded as optional derived entries in `inputs.lock.json`.
5. Build a writable test NAND from the extracted system tree:

```powershell
python tooling/build_h1_system_nand.py `
  --template .local/derived/h1-v1-template.raw `
  --system-data .local/derived/v1-system-data `
  --output .local/build/h1-v1-system.raw `
  --manifest .local/build/h1-v1-system.json `
  --python-ecc
```

6. Launch the pinned emulator with 64 MiB and single-threaded TCG. Do not publish `.local/` or use host acceleration to claim device-equivalent performance.
7. Run `python scripts/verify_source_project.py`, build a Git archive, and run `python tooling/audit_release_secrets.py <archive>` before publishing source changes.

The proprietary archive-to-template extraction remains a user-owned input step; the public project makes all later transforms and hashes reviewable without redistributing vendor data.
