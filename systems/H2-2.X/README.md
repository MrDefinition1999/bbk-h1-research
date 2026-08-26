# 步步高 @ibox H2 V2.2L 模拟器与逆向工程

本目录保存 H2 V2.2L 的可复现镜像工具、Windows ARM64 模拟器和“使命”H2 专用移植层。实现主线来自 [zhiyb 的 H2 逆向文章](https://zhiyb.github.io/blog/2026/05/23/Reverse-engineering-BBK-ibox-H2/)及文章公开的 OpenNoah QEMU/BootROM 仓库。

H2 项目不使用 H1 模拟器文件或 H1 固件。H1 文档仅提供 ABI 映射、内存接管、跟踪和恢复方法经验。运行机器始终是 `bbk_iboxh2`、JZ4750L、32 MiB SDRAM、480×272 LCD、MSC0/eMMC、H2 SADC 触摸和七个 H2 GPIO 键；不虚构全键盘或联机芯片。

## 本地运行

ARM64 运行目录中执行：

```powershell
.\start-h2.cmd --persistent
```

当前开发工作区使用固定地址：

```text
http://127.0.0.1:8797/
```

页面风格、状态区和启动/停止/重启方式与 H1 模拟器保持一致，并会在 QEMU 重启后自动重连。页面只暴露 H2 的左、右、确认、返回、音量－、音量＋和电源七键；使命内音量－/＋临时作为下/上。

本项目只构建和保留 Windows ARM64 运行包，不生成 x86-64 模拟器。

## 当前状态

- H2 原生 BootROM→MSC0/eMMC→H2L→系统→桌面链路已验证。
- 模拟器专用 WAIT 唤醒修正解决约一分钟后的假死。
- “使命”可启动并进入创建角色和剧情；任务场景目前因 32 MiB 布局下的真实堆分配失败而显示异常，尚不可称为可游玩。
- 七键转换、左右 GPIO 唤醒、32 位画面接管及堆区避让已实现。
- 不提高模拟器 RAM；下一步是在实机容量内降低场景切换峰值，之后再做实体 H2、音频、存档/读档和长时间游戏复验。

详细设计和边界见 [使命移植报告](docs/mission-feasibility.md)，完整构建过程见 [本地复现](docs/reproduce.md)。

## 发布边界

官方恢复包、派生 eMMC 镜像、QEMU 可执行文件、DLL 和“使命”资源均保留在被忽略的本地运行目录，不进入源代码发布包。交付前必须运行：

```powershell
python scripts/audit_release_secrets.py systems/H2-2.X
```

最终 ZIP 本身也必须再次扫描。
