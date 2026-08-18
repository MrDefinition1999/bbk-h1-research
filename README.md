# BBK H1 逆向研究

这是 BBK `@ibox H1` 学习机的可复现逆向研究与工具仓库，覆盖 JZ4740/XBurst
硬件、BDA 应用格式、NAND/FTL、固件启动路径、H1 模拟器以及 1.X/2.X 系统差异。

## 系统项目

- [`systems/1.X`](systems/1.X)：1.X 独立复现入口、官方输入哈希和当前验证状态。
- [`systems/2.X`](systems/2.X)：2.X 独立复现入口、V2 NAND 重建和 V1 游戏兼容研究。

这两个目录分别发布为 [`bbk-h1-1x`](https://github.com/MrDefinition1999/bbk-h1-1x)
与 [`bbk-h1-2x`](https://github.com/MrDefinition1999/bbk-h1-2x)。它们只包含源码、文档、输入哈希和固定组件版本；厂商固件、NAND、商业游戏、IDA 数据库和生成二进制均不进入 Git。

## 仓库边界

- `docs/`：已确认结论、验证记录、未决问题和持续研究状态。
- `scripts/`：固件、NAND/FTL、BDA、模拟器、拆分发布和隐私审计工具。
- `systems/`：两个版本各自独立的轻量源码项目。

公开 SDK 和模拟器分别维护于
[`bbk-h1-bda-sdk`](https://github.com/MrDefinition1999/bbk-h1-bda-sdk) 与
[`bbk-h1-emulator`](https://github.com/MrDefinition1999/bbk-h1-emulator)，具体边界见[开源项目结构](docs/15-open-source-projects.md)。

原创源码和文档采用 [Apache License 2.0](LICENSE)。第三方界面与素材边界见 [NOTICE](NOTICE)。

English: [README.en.md](README.en.md)
