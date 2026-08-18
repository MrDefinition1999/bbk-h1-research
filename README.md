# BBK H1 逆向研究

这是 BBK `@ibox H1` 学习机的可复现逆向研究与工具仓库，覆盖 JZ4740/XBurst
硬件、BDA 应用格式、NAND/FTL、固件启动路径和 H1 模拟器验证。

从[研究笔记](docs/README.md)开始，笔记区分已确认事实、推断、未决问题和复现步骤。

## 仓库边界

- `docs/`：逆向结论、验证记录和研究方法。
- `scripts/`：固件、NAND/FTL、BDA、测试和隐私审计工具。
- SDK、模拟器和 KOV 游戏移植分别维护，边界见[开源项目拆分](docs/15-open-source-projects.md)。

固件、NAND、恢复包、ROM、IDA 数据库、运行日志、工具链和生成的二进制文件不进入本仓库。
KOV PGM 移植和实机测试包仍是本地私有研究成果，不是本仓库的发布内容。

English version: [README.en.md](README.en.md)

## 许可

原创源代码和文档采用 [Apache License 2.0](LICENSE)。截图及其中展示的第三方界面或素材仅作为研究证据，具体边界见 [NOTICE](NOTICE)。
