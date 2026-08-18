# BBK H1 1.X 可复现项目

本仓库是 BBK `@ibox H1` 1.X 系统的独立、源码化复现入口。它固定公开 SDK 和模拟器的版本，记录合法输入的 SHA-256，并提供 NAND/FAT/FTL、BDA 与模拟器工具；厂商固件、NAND、商业游戏和生成二进制不会进入 Git。

## 快速开始

```powershell
python .\scripts\bootstrap_components.py
python .\scripts\verify_inputs.py
python .\scripts\verify_source_project.py
```

把自己合法取得的两个 V1.41 恢复包放到 `.local/inputs/`，文件名和哈希见 `inputs.lock.json`。完整步骤见 [复现说明](docs/reproduce.md)，当前验证状态见 [1.X 状态](docs/1x-status.md)。

KOV/PGM ROM、PAK 和来源许可未解决的移植源码不属于本仓库。公开代码和文档采用 Apache-2.0；拉取的模拟器组件保留 GPL/QEMU 上游许可。

English: [README.en.md](README.en.md)
