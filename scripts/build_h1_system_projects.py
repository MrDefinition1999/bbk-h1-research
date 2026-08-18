#!/usr/bin/env python3
"""Materialize the small, source-only H1 1.X and 2.X project directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "systems"
SDK_COMMIT = "352889b9fa9750cd8e4cb4806e5fc0e8edeac211"
EMULATOR_COMMIT = "2416cfc4bb5295a1dad44c1129159620416b3862"

COMMON_GITIGNORE = """# Proprietary and generated local state
/.local/
/build/
/dist/
__pycache__/
*.py[cod]
*.log
*.raw
*.rom
*.bin
*.bda
*.dlx
*.pak
*.rar
*.7z
*.zip
*.exe
*.dll
*.elf
*.i64
*.id0
*.id1
*.id2
*.nam
*.til
"""

BOOTSTRAP = r'''#!/usr/bin/env python3
"""Clone and pin the public SDK and emulator components."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "components.lock.json"
COMPONENTS = ROOT / ".local" / "components"


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        list(args), cwd=cwd, check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def main() -> int:
    records = json.loads(LOCK.read_text(encoding="utf-8"))["components"]
    COMPONENTS.mkdir(parents=True, exist_ok=True)
    for record in records:
        destination = COMPONENTS / record["directory"]
        if not (destination / ".git").is_dir():
            if destination.exists():
                raise SystemExit(f"refusing non-Git component directory: {destination}")
            run("git", "clone", "--filter=blob:none", "--no-checkout", record["url"], str(destination))
        remote = run("git", "remote", "get-url", "origin", cwd=destination)
        if remote.rstrip("/").removesuffix(".git") != record["url"].rstrip("/").removesuffix(".git"):
            raise SystemExit(f"unexpected origin for {record['name']}: {remote}")
        run("git", "fetch", "--depth=1", "origin", record["commit"], cwd=destination)
        run("git", "checkout", "--detach", record["commit"], cwd=destination)
        actual = run("git", "rev-parse", "HEAD", cwd=destination)
        if actual != record["commit"]:
            raise SystemExit(f"commit mismatch for {record['name']}: {actual}")
        print(f"{record['name']}={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

VERIFY_INPUTS = r'''#!/usr/bin/env python3
"""Verify user-supplied and derived private inputs without publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    records = json.loads((ROOT / "inputs.lock.json").read_text(encoding="utf-8"))["files"]
    verified = 0
    missing = []
    for record in records:
        path = ROOT / record["path"]
        if not path.is_file():
            if record.get("required", False):
                missing.append(record["path"])
            continue
        size = path.stat().st_size
        actual = digest(path)
        if size != record["bytes"] or actual != record["sha256"]:
            raise SystemExit(
                f"input mismatch: {record['path']} bytes={size} sha256={actual}"
            )
        verified += 1
        print(f"verified={record['path']}")
    if missing and not args.allow_missing:
        raise SystemExit("missing required inputs: " + ", ".join(missing))
    print(f"verified_files={verified} missing_required={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

VERIFY_PROJECT = r'''#!/usr/bin/env python3
"""Check the source-only repository boundary before publishing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".local", "build", "dist", "__pycache__"}
PROHIBITED = {
    ".7z", ".bda", ".bin", ".dll", ".dlx", ".elf", ".exe", ".i64",
    ".id0", ".id1", ".id2", ".log", ".nam", ".pak", ".rar", ".raw",
    ".rom", ".til", ".zip",
}


def files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.relative_to(ROOT).parts):
            continue
        yield path


def main() -> int:
    required = {
        "README.md", "README.en.md", "LICENSE", "NOTICE",
        "components.lock.json", "inputs.lock.json", "docs/reproduce.md",
        "scripts/bootstrap_components.py", "scripts/verify_inputs.py",
        "tooling/audit_release_secrets.py",
    }
    present = {path.relative_to(ROOT).as_posix() for path in files()}
    missing = sorted(required - present)
    if missing:
        raise SystemExit("missing project files: " + ", ".join(missing))
    prohibited = sorted(
        path.relative_to(ROOT).as_posix()
        for path in files()
        if path.suffix.casefold() in PROHIBITED
    )
    if prohibited:
        raise SystemExit("proprietary/generated files entered source tree: " + ", ".join(prohibited))
    lock = json.loads((ROOT / "components.lock.json").read_text(encoding="utf-8"))
    for record in lock["components"]:
        commit = record["commit"]
        if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
            raise SystemExit(f"invalid pinned commit for {record['name']}: {commit}")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_inputs.py"), "--allow-missing"],
        cwd=ROOT,
        check=True,
    )
    print(f"source_files={len(present)} prohibited=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

V1_README = """# BBK H1 1.X 可复现项目

本仓库是 BBK `@ibox H1` 1.X 系统的独立、源码化复现入口。它固定公开 SDK 和模拟器的版本，记录合法输入的 SHA-256，并提供 NAND/FAT/FTL、BDA 与模拟器工具；厂商固件、NAND、商业游戏和生成二进制不会进入 Git。

## 快速开始

```powershell
python .\\scripts\\bootstrap_components.py
python .\\scripts\\verify_inputs.py
python .\\scripts\\verify_source_project.py
```

把自己合法取得的两个 V1.41 恢复包放到 `.local/inputs/`，文件名和哈希见 `inputs.lock.json`。完整步骤见 [复现说明](docs/reproduce.md)，当前验证状态见 [1.X 状态](docs/1x-status.md)。

KOV/PGM ROM、PAK 和来源许可未解决的移植源码不属于本仓库。公开代码和文档采用 Apache-2.0；拉取的模拟器组件保留 GPL/QEMU 上游许可。

English: [README.en.md](README.en.md)
"""

V1_README_EN = """# Reproducible BBK H1 1.X project

This is the source-only reproduction entry point for BBK `@ibox H1` 1.X. It pins the public SDK and emulator revisions, records SHA-256 identities for lawful user-supplied inputs, and carries the NAND/FAT/FTL, BDA, and emulator tooling needed to repeat the research. Vendor firmware, NAND images, commercial games, and generated binaries never enter Git.

```powershell
python .\\scripts\\bootstrap_components.py
python .\\scripts\\verify_inputs.py
python .\\scripts\\verify_source_project.py
```

Place your two lawful V1.41 recovery packages in `.local/inputs/`; exact names and hashes are in `inputs.lock.json`. See [reproduction](docs/reproduce.md) and [current status](docs/1x-status.md).

KOV/PGM ROMs, PAK files, and port sources with unresolved provenance are excluded. Original project code and documentation use Apache-2.0; the fetched emulator retains GPL/QEMU upstream terms.

中文: [README.md](README.md)
"""

V2_README = """# BBK H1 2.X 可复现项目

本仓库是 BBK `@ibox H1` 2.X 系统的独立、源码化复现入口。它固定公开 SDK 和模拟器版本，记录 V2.20 官方输入及派生组件的 SHA-256，并包含 V2 NAND 重建和 V1 游戏 ABI 兼容层工具；厂商包、NAND、BDA、游戏数据和生成二进制不会进入 Git。

```powershell
python .\\scripts\\bootstrap_components.py
python .\\scripts\\verify_inputs.py
python .\\scripts\\verify_source_project.py
```

把自己合法取得的 V2.20 PC/SD 恢复包放到 `.local/inputs/`。完整步骤见 [复现说明](docs/reproduce.md)，持续研究状态见 [2.X 状态](docs/2x-status.md) 和 [V1 游戏兼容状态](docs/v1-game-compat-status.md)。

公开代码和文档采用 Apache-2.0；拉取的模拟器组件保留 GPL/QEMU 上游许可。

English: [README.en.md](README.en.md)
"""

V2_README_EN = """# Reproducible BBK H1 2.X project

This is the source-only reproduction entry point for BBK `@ibox H1` 2.X. It pins the public SDK and emulator revisions, records SHA-256 identities for official V2.20 inputs and derived components, and includes the V2 NAND reconstruction plus V1-game ABI compatibility tooling. Vendor packages, NAND images, BDAs, game data, and generated binaries never enter Git.

```powershell
python .\\scripts\\bootstrap_components.py
python .\\scripts\\verify_inputs.py
python .\\scripts\\verify_source_project.py
```

Place your lawful V2.20 PC and SD recovery packages in `.local/inputs/`. See [reproduction](docs/reproduce.md), [2.X status](docs/2x-status.md), and [V1 game compatibility status](docs/v1-game-compat-status.md).

Original project code and documentation use Apache-2.0; the fetched emulator retains GPL/QEMU upstream terms.

中文: [README.md](README.md)
"""

V1_REPRODUCE = """# 1.X reproduction

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
"""

V2_REPRODUCE = """# 2.X reproduction

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
"""


def component_lock() -> dict[str, object]:
    return {
        "format": "bbk-h1-components-v1",
        "components": [
            {
                "name": "bbk-h1-bda-sdk",
                "directory": "sdk",
                "url": "https://github.com/MrDefinition1999/bbk-h1-bda-sdk.git",
                "commit": SDK_COMMIT,
                "license": "Apache-2.0",
            },
            {
                "name": "bbk-h1-emulator",
                "directory": "emulator",
                "url": "https://github.com/MrDefinition1999/bbk-h1-emulator.git",
                "commit": EMULATOR_COMMIT,
                "license": "GPL-2.0-and-upstream-QEMU-terms",
            },
        ],
    }


V1_INPUTS = {
    "format": "bbk-h1-inputs-v1",
    "files": [
        {"path": ".local/inputs/@ibox H1 V1.41CJXTHF.rar", "bytes": 467351318, "sha256": "0FD2ADB0C3AFFD71577CEDF5C6267151661B46A623F888E05B6EB6AF9EA2CBC1", "required": True, "kind": "official"},
        {"path": ".local/inputs/H1 V1.41SDKHF.rar", "bytes": 431553838, "sha256": "0F65CF4CC7D4D099376F218A5845F223F548340F528AF5B6969ACC7A5AB63A4A", "required": True, "kind": "official"},
        {"path": ".local/derived/project.bin", "bytes": 5729640, "sha256": "D05786E442F9AAD62A8D0A0CB4F6D786BDC7C2FA353A7A2B152C9ED9F01B40EF", "required": False, "kind": "derived"},
        {"path": ".local/derived/h1-v1-template.raw", "bytes": 1107296256, "sha256": "614B0E5F85CA262A84BF26C7AD024043B32CE4CC6756D1C741E006846E134012", "required": False, "kind": "derived"},
    ],
}

V2_INPUTS = {
    "format": "bbk-h1-inputs-v2",
    "files": [
        {"path": ".local/inputs/H1-V2.20-super-recovery.exe", "bytes": 462206976, "sha256": "8F4B305777C3DD36E5FB460D9CCBE5F3D397999CF832C82895F074FC8761681F", "required": True, "kind": "official"},
        {"path": ".local/inputs/H1-V2.20-SD-recovery.rar", "bytes": 443697917, "sha256": "794B8D79B15847B35916CE6BB7B0D39D59F5D2D470F18D8453AC8E71EF97EB54", "required": True, "kind": "official"},
        {"path": ".local/derived/v2-loader.bin", "bytes": 5192, "sha256": "B8F5D40381672D27854FDCA5D8FE480EF6D3DA317096CFC8EE8A25B18D37F160", "required": False, "kind": "derived"},
        {"path": ".local/derived/v2-uboot.bin", "bytes": 44624, "sha256": "8577B6CAE9B90866B898FEDF3FA3ABB1FB88A2098E16A0E36E39E9BED605C8A1", "required": False, "kind": "derived"},
        {"path": ".local/derived/v2-os.bin", "bytes": 796272, "sha256": "FA77B06A6C0D1679FE672FC9ABC7C3A7E4EA9374F8D5A6E6A9D2686D1891886C", "required": False, "kind": "derived"},
        {"path": ".local/derived/v2-extos1.bin", "bytes": 3676424, "sha256": "BE6313C6C634E00331C463DFC12C92DEDFD43BCF173A58EF5CA4BDB062B62767", "required": False, "kind": "derived"},
        {"path": ".local/derived/v2-extos2.bin", "bytes": 1150608, "sha256": "339BE4FEB60565EA475C17A2EA668C0FBC58ADE9E83380ADF6A25028EDABC57C", "required": False, "kind": "derived"},
        {"path": ".local/derived/h1-v2-system.raw", "bytes": 1107296256, "sha256": "8283D51E341B3552FC4EC9BDBBD57640AA4D01C86B46C616F587FFD709A59151", "required": False, "kind": "derived"},
    ],
}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def copy_text(source: Path, destination: Path) -> None:
    write_text(destination, source.read_text(encoding="utf-8"))


def materialize(project: Path, version: str) -> None:
    project.mkdir(parents=True, exist_ok=True)
    write_text(project / ".gitignore", COMMON_GITIGNORE)
    copy_text(ROOT / "LICENSE", project / "LICENSE")
    copy_text(ROOT / "NOTICE", project / "NOTICE")
    write_json(project / "components.lock.json", component_lock())
    write_text(project / "scripts" / "bootstrap_components.py", BOOTSTRAP)
    write_text(project / "scripts" / "verify_inputs.py", VERIFY_INPUTS)
    write_text(project / "scripts" / "verify_source_project.py", VERIFY_PROJECT)

    excluded = {"build_h1_system_projects.py", "recycle_h1_transients.ps1"}
    for source in sorted((ROOT / "scripts").iterdir()):
        if not source.is_file() or source.name in excluded:
            continue
        if source.suffix.casefold() not in {".py", ".ps1", ".c", ".mjs"}:
            continue
        copy_text(source, project / "tooling" / source.name)

    if version == "1.X":
        write_text(project / "README.md", V1_README)
        write_text(project / "README.en.md", V1_README_EN)
        write_json(project / "inputs.lock.json", V1_INPUTS)
        write_text(project / "docs" / "reproduce.md", V1_REPRODUCE)
        copy_text(ROOT / "docs" / "17-v1-validation.md", project / "docs" / "1x-status.md")
        copy_text(ROOT / "docs" / "13-kov-pgm.md", project / "docs" / "kov-research-status.md")
    else:
        write_text(project / "README.md", V2_README)
        write_text(project / "README.en.md", V2_README_EN)
        write_json(project / "inputs.lock.json", V2_INPUTS)
        write_text(project / "docs" / "reproduce.md", V2_REPRODUCE)
        copy_text(ROOT / "docs" / "16-v2-system.md", project / "docs" / "2x-status.md")
        copy_text(ROOT / "docs" / "19-v1-v2-mission-handoff.md", project / "docs" / "v1-game-compat-status.md")


def tree_digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        value.update(len(relative).to_bytes(4, "little"))
        value.update(relative)
        value.update(path.read_bytes())
    return value.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    projects = (("1.X", output / "1.X"), ("2.X", output / "2.X"))
    for version, project in projects:
        materialize(project, version)
        print(f"{version}={project} files={sum(p.is_file() for p in project.rglob('*'))} sha256={tree_digest(project)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
