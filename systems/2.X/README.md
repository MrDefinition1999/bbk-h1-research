# BBK H1 2.X 可复现项目

本仓库是 BBK `@ibox H1` 2.X 系统的独立、源码化复现入口。它固定公开 SDK 和模拟器版本，记录 V2.20 官方输入及派生组件的 SHA-256，并包含 V2 NAND 重建和 V1 游戏 ABI 兼容层工具；厂商包、NAND、BDA、游戏数据和生成二进制不会进入 Git。

```powershell
python .\scripts\bootstrap_components.py
python .\scripts\verify_inputs.py
python .\scripts\verify_source_project.py
```

把自己合法取得的 V2.20 PC/SD 恢复包放到 `.local/inputs/`。完整步骤见 [复现说明](docs/reproduce.md)，持续研究状态见 [2.X 状态](docs/2x-status.md) 和 [V1 游戏兼容状态](docs/v1-game-compat-status.md)。

公开代码和文档采用 Apache-2.0；拉取的模拟器组件保留 GPL/QEMU 上游许可。

English: [README.en.md](README.en.md)
