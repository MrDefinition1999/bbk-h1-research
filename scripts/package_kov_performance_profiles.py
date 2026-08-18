#!/usr/bin/env python3
"""Build and audit the private ROM-free KOV real-device test package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "h1-bda-sdk" / "ports" / "kov_pgm"
DELIVERABLES = ROOT / "deliverables"
RELEASE_NAME = "H1-KOV-Plus-performance-v7-2026-08-17"
SOURCE_DATE_EPOCH = "1786924800"
ZIP_TIMESTAMP = (2026, 8, 17, 0, 0, 0)
BDA_NAMES = (
    "H1KOVPlus-base.bda",
    "H1KOVPlus-336MHz.bda",
    "H1KOVPlus-336MHz-30FPS.bda",
    "H1KOVPlus-384MHz.bda",
    "H1KOVPlus-384MHz-30FPS.bda",
)
EXPECTED_TITLES = {
    "H1KOVPlus-base.bda": "\u4e09\u56fd\u6218\u7eaa",
    "H1KOVPlus-336MHz.bda": "\u4e09\u56fd336",
    "H1KOVPlus-336MHz-30FPS.bda": "\u4e09\u56fd336\u5e27",
    "H1KOVPlus-384MHz.bda": "\u4e09\u56fd384",
    "H1KOVPlus-384MHz-30FPS.bda": "\u4e09\u56fd384\u5e27",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def generated_path(path: Path) -> Path:
    resolved = path.resolve()
    root = DELIVERABLES.resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"refusing output outside deliverables: {resolved}")
    return resolved


def run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
    )


def write_text_files(stage: Path) -> None:
    (stage / "README.md").write_text(
        """# BBK H1 三国战纪+ 性能测试包 V7

本包用于实机性能和稳定性测试，不含游戏 ROM、PGM BIOS 或 `KOVH1.PAK`。
请勿公开分发本包；KOV 相关 CPU 核心和驱动的再发布许可仍在核查。

V7 在 V6 的实机时钟、调度和跳帧策略上，只新增 ICS2115 活跃声部混音优化：每个音频缓冲先收集实际活跃声部，并复用不变的步长、音量和循环边界。游戏逻辑帧、音频采样率、采样读取顺序和声部地址推进均未改变。`KOVPERF.TXT` 中应显示 `audio_mixer_version=2`。

## 版本选择

- `H1KOVPlus-base.bda`：原频，启用 JZ4740 IRQ-idle 优化、原生 448x224 提交、自适应跳帧和 80 Hz 调度。
- `H1KOVPlus-336MHz.bda`：与基础版相同，并记录 `KOVPERF.TXT`；在原生 336 MHz 设备上不会改写时钟。
- `H1KOVPlus-336MHz-30FPS.bda`：原生 336 MHz，每个逻辑帧仍运行，只固定隔帧渲染，目标约 30 FPS。
- `H1KOVPlus-384MHz.bda`：在校验 JZ4740 时钟源和分频上限后临时请求 384 MHz，并在正常或错误退出时恢复原时钟。
- `H1KOVPlus-384MHz-30FPS.bda`：与 384 MHz 版相同，但固定隔帧渲染，目标约 30 FPS。

请一次只安装一个版本。建议按基础版、336 MHz、自适应 384 MHz、固定 30 FPS 的顺序测试。408 MHz 已在实机上表现不稳定，本包不提供。

若要判断 V7 优化是否对实机有效，请在同一关卡、同一人数和相近敌人数量下，优先对比 V6 与 V7 的 `336MHz-30FPS` 版本；不要根据 PC 微基准或模拟器流畅度判断收益。

## 安装

1. 将所选 BDA 改名为 `KOV.bda`，再放到 `A:\\应用\\程序`。
2. 将自己合法持有的私有数据包放到 `A:\\应用\\数据\\KOVH1\\KOVH1.PAK`。
3. 从 H1 的“其它”应用页启动对应图标。

## 操作

方向键或 W/A/S/D 移动，J/K/U/I 为四个动作键，确认键或 Enter 为 Start，Space 投币，P 暂停。长按返回键或 Esc 约 0.75 秒退出。

## 实机测试建议

每个版本至少运行 10 分钟，并测试战斗、多人同屏、音效密集场景、暂停和正常退出。所有 336/384 版正常退出后，请保留 `A:\\应用\\数据\\KOVH1\\KOVPERF.TXT`，并记录主观速度是否接近街机。384 MHz 若出现花屏、重启、死机或存储异常，请立即停止使用并回到 336 MHz。

每次测试正常退出后，必须先把 `KOVPERF.TXT` 复制到 PC，并分别改名为 `KOVPERF-336.txt`、`KOVPERF-336-30FPS.txt`、`KOVPERF-384.txt` 或 `KOVPERF-384-30FPS.txt`；下一次启动 KOV 会清空上一次日志。

模拟器只用于启动、输入、音频、退出和结构回归，不用于判断实机 FPS。性能结论只接受实机 `KOVPERF.TXT` 和实际游玩反馈。

文件哈希见 `SHA256SUMS.txt`。英文说明见 `README.en.md`。
""",
        encoding="utf-8",
        newline="\n",
    )
    (stage / "README.en.md").write_text(
        """# BBK H1 KOV Plus performance test package V7

This package is for private real-device performance and stability testing. It contains no game ROM, PGM BIOS, or `KOVH1.PAK`. Do not redistribute it publicly while the redistribution terms of the KOV CPU cores and driver remain unresolved.

V7 keeps the V6 real-device clock, scheduler, and frame-skip policies and changes only the ICS2115 mixer. Each audio buffer now collects the active voices once and reuses invariant step, volume, and loop values. Logical frames, sample rate, sample-read order, and voice-address progression are unchanged. `KOVPERF.TXT` should report `audio_mixer_version=2`.

## Profiles

- `H1KOVPlus-base.bda`: stock clock, JZ4740 IRQ-idle optimization, native 448x224 presentation, adaptive frame skipping, and an 80 Hz scheduler.
- `H1KOVPlus-336MHz.bda`: the same runtime plus `KOVPERF.TXT` profiling; it does not rewrite clocks on a native 336 MHz device.
- `H1KOVPlus-336MHz-30FPS.bda`: native 336 MHz with every logic frame preserved and every other render/present skipped, targeting about 30 FPS.
- `H1KOVPlus-384MHz.bda`: temporarily requests 384 MHz after validating the JZ4740 source clock and divider limits, then restores the original clock on normal or error exit.
- `H1KOVPlus-384MHz-30FPS.bda`: the 384 MHz profile with the same fixed alternate-frame rendering policy.

Install one profile at a time. Test base, adaptive 336 MHz, adaptive 384 MHz, then the fixed 30 FPS profiles. The physically unstable 408 MHz profile is intentionally excluded.

To measure the V7 change on hardware, compare the V6 and V7 `336MHz-30FPS` profiles in the same stage with the same player and approximate enemy count. Do not infer the gain from the PC microbenchmark or emulator smoothness.

## Installation

1. Rename the selected BDA to `KOV.bda`, then put it under `A:\\应用\\程序`.
2. Put your privately generated, lawfully owned data pack at `A:\\应用\\数据\\KOVH1\\KOVH1.PAK`.
3. Launch the matching icon from the H1 Other applications page.

Arrow keys or W/A/S/D move; J/K/U/I are the four action buttons; Confirm or Enter is Start; Space inserts a coin; P pauses. Hold Back or Escape for about 0.75 seconds to exit.

Run each profile for at least ten minutes, including busy battles, audio-heavy scenes, pause, and normal exit. Keep `A:\\应用\\数据\\KOVH1\\KOVPERF.TXT` from every 336/384 MHz profile and note whether gameplay speed feels arcade-accurate. Stop using 384 MHz immediately if the device shows corruption, reboots, freezes, or reports storage errors.

After each normal exit, copy `KOVPERF.TXT` to the PC before the next launch and name it `KOVPERF-336.txt`, `KOVPERF-336-30FPS.txt`, `KOVPERF-384.txt`, or `KOVPERF-384-30FPS.txt`. The next KOV launch clears the previous journal.

The emulator is used only for boot, input, audio, exit, and structural regression. Physical performance claims require real-device `KOVPERF.TXT` data and gameplay feedback.

See `SHA256SUMS.txt` for file hashes.
""",
        encoding="utf-8",
        newline="\n",
    )


def write_checksums(stage: Path) -> None:
    lines = [f"{sha256(stage / name)}  {name}" for name in BDA_NAMES]
    (stage / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="ascii", newline="\n"
    )


def validate_bdas(stage: Path, environment: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="kov-bda-validation-") as temporary:
        report_path = Path(temporary) / "icons.json"
        run(
            [
                sys.executable,
                str(ROOT / "h1-bda-sdk" / "scripts" / "audit_release_icons.py"),
                str(stage),
                "--expected-count",
                str(len(BDA_NAMES)),
                "--output",
                str(report_path),
            ],
            environment=environment,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
    observed = {item["file"]: item["title"] for item in report["games"]}
    if observed != EXPECTED_TITLES:
        raise SystemExit(f"unexpected BDA titles: {observed!r}")


def build_archive(stage: Path, archive: Path) -> None:
    with zipfile.ZipFile(
        archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as output:
        for path in sorted(
            (item for item in stage.iterdir() if item.is_file()),
            key=lambda item: item.name.casefold(),
        ):
            info = zipfile.ZipInfo(path.name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, path.read_bytes(), compresslevel=9)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, default=DELIVERABLES / RELEASE_NAME)
    parser.add_argument("--archive", type=Path, default=DELIVERABLES / f"{RELEASE_NAME}.zip")
    args = parser.parse_args()
    stage = generated_path(args.stage)
    archive = generated_path(args.archive)
    if stage.exists() or archive.exists():
        raise SystemExit("release target already exists; move it to the Recycle Bin first")

    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="kov-performance-release-") as temporary:
        built = Path(temporary) / "profiles"
        run(
            [
                sys.executable,
                str(PORT / "build_profiles.py"),
                "--output-directory",
                str(built),
                "--verify-reproducible",
            ],
            environment=environment,
        )
        stage.mkdir(parents=True)
        for name in BDA_NAMES:
            shutil.copyfile(built / name, stage / name)

    write_text_files(stage)
    write_checksums(stage)
    validate_bdas(stage, environment)
    auditor = ROOT / "scripts" / "audit_release_secrets.py"
    run([sys.executable, str(auditor), str(stage)], environment=environment)
    build_archive(stage, archive)
    run([sys.executable, str(auditor), str(archive)], environment=environment)
    print(f"stage={stage}")
    print(f"archive={archive} size={archive.stat().st_size} sha256={sha256(archive)}")
    for name in BDA_NAMES:
        print(f"{name} size={(stage / name).stat().st_size} sha256={sha256(stage / name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
