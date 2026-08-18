# 2.X reproduction

## Requirements

- Windows PowerShell, Git, Python 3.10+, and 7-Zip.
- A MIPS little-endian toolchain for SDK and compatibility applications.
- The lawful V2.20 PC and SD recovery packages listed in `inputs.lock.json`.

## Procedure

1. Run `python scripts/bootstrap_components.py` and `python scripts/verify_inputs.py`.
2. Extract the SD package under `.local/extracted/v2-sd/` without committing it.
3. Stream the authoritative 307-file PC member (offset `5945383`) into a private tree:

```powershell
python tooling/extract_h1_v2_pc_member.py `
  .local/extracted/v2-sd/@ibox_H1_系统恢复程序.upd `
  .local/inputs/H1-V2.20-super-recovery.exe `
  5945383 `
  --out .local/derived/v2-system-data `
  --json .local/build/v2-pc-indexed.json
```

4. Derive Loader, U-Boot, OS, ExtOs1 and ExtOs2 from your own recovery package. Validate their exact sizes and SHA-256 values against `inputs.lock.json`.
5. Use the native V2 template and build the NAND:

```powershell
python tooling/build_h1_v2_nand.py `
  --template .local/derived/h1-v2-native-template.raw `
  --system-data .local/derived/v2-system-data `
  --loader .local/derived/v2-loader.bin `
  --uboot .local/derived/v2-uboot.bin `
  --os .local/derived/v2-os.bin `
  --extos1 .local/derived/v2-extos1.bin `
  --extos2 .local/derived/v2-extos2.bin `
  --output .local/build/h1-v2-system.raw `
  --manifest .local/build/h1-v2-system.json
```

6. Validate direct-OS and complete BootROM boot with the pinned emulator at 64 MiB, single-threaded TCG, and the V2 touch profile.
7. Run `python scripts/verify_source_project.py`, build a Git archive, and run `python tooling/audit_release_secrets.py <archive>` before publishing source changes.

V1 game compatibility is an application-level ABI layer; it does not authorize distribution of original V1 games or Mission data.
