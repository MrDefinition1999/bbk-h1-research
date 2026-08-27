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
- 2026-08-26 的 H1 V1 使命负载曾进入主菜单、创建角色和剧情；任务场景在 32 MiB 布局中命中真实堆分配失败并显示异常。这是保留的历史阶段性结果，不是当前活动镜像。
- 2026-08-27 的当前活动镜像改用原版 S1 使命负载。stage 已到 `game-start`，H2 原生 shell 句柄也非零，但可见前台仍停在词典 UI；S1 分支尚未显示游戏首窗，更不能称为可玩。
- 当前问题已缩小到 S1→H2 前台/窗口 ABI，优先核对 S1 `GUI+0x084` 的 320×240 描述符与 H2 `GUI+0x07C`，不要再从导航或 B 盘资源开始排查。
- 固定导航已编码为 `tooling/navigate_h2_mission.py`：等待开机卡顿窗口、进入工具娱乐第二页、触摸选择箭头/图标并用硬件确认激活，再通过 trace 验证，不依赖截图。
- 不提高模拟器 RAM；真实 H2、音频、存档/读档和长时间游戏都尚未验收。

详细设计和两条实验分支见 [使命移植报告](docs/mission-feasibility.md)，完整构建过程见 [本地复现](docs/reproduce.md)。跨 H1/H2 的完整交接见仓库根目录 `docs/22-current-project-handoff.md`。

## 发布边界

官方恢复包、派生 eMMC 镜像、QEMU 可执行文件、DLL 和“使命”资源均保留在被忽略的本地运行目录，不进入源代码发布包。交付前必须运行：

```powershell
python scripts/audit_release_secrets.py systems/H2-2.X
```

最终 ZIP 本身也必须再次扫描。
