# 下一位 AI 启动与续研提示词

更新：2026-08-27（Asia/Irkutsk）

复制下面四条反引号之间的全部内容，作为下一位 AI 在本项目中的第一条用户消息。该提示词要求 AI 先完成资料接管和三模拟器人工验收，等待用户明确确认后，才继续 S1 原版使命到 H2 的移植。

````text
你将接手 `BBK H1 Reverse GPT` 项目。工作区根目录是当前打开的项目目录。不要从零猜测，也不要立刻继续逆向；先按下面的阶段和原则完成接管。

# 总目标与停顿点

本次分两个阶段：

1. 第一阶段只做资料读取、状态核验、启动 H1 V1.41、H1 V2.20、H2 V2.2L 三个本地 ARM64 模拟器，并让我在浏览器里人工确认。
2. 三个模拟器都启动并给出浏览器地址后，必须停止操作并等待我明确回复“确认，可以继续”或同等含义。没有我的确认，不得进入使命、不得改镜像、不得继续 S1 逆向。
3. 我确认后，才进入第二阶段：继续尚未完成的“原版 S1 使命→H2 V2.2L”移植，目标是在 H2 实机等同的 32 MiB RAM 内取得正确可见前台并逐步达到可玩。

# 始终遵守的原则

## 1. 数据安全与删除

- 任何删除前先做只读检查，解析出精确绝对路径、文件类型、大小、用途和恢复方式。
- Windows 上使用同一个 PowerShell 环境完成核对和回收；优先移入 Windows 回收站，不直接永久删除。
- 先 `-WhatIf` 或等价 dry-run，再执行，再验证目标消失和核心文件仍在。
- 禁止对工作区根目录、用户目录、磁盘根目录、未解析变量、通配根路径执行递归删除。
- 不得使用 `git reset --hard`、`git checkout --` 或其他会覆盖用户修改的命令。
- 当前 `scripts/qemu_gdb_read.py` 有用户自己的未提交改动，始终保留、不要暂存、不要覆盖、不要提交。
- 不得删除当前 H2 活动 eMMC、当前 S1 资源、最后安装 manifest 或活动回滚链。当前已撤销的 `undo-h1v1-current.sectors.gz` 已于 2026-08-27 清理，不属于活动链。
- 对可再生缓存、截图、日志和失败构建：先把结论写入文档，再及时回收；大文件删除后说明能否恢复。

## 2. 项目体积硬上限

- 项目目录硬上限为 15 GiB，当前清理后基线约 10.811 GiB。
- 每次开始和结束工作都统计项目总字节数与顶层目录大小，并在进度消息中报告。
- 任何可能生成完整 NAND/eMMC、副本、工具链或大跟踪文件的操作，先估算峰值；预计会达到 15 GiB 时必须停止，先清理或向我确认。
- 14.5 GiB 视为预警线。一次只保留一个必要的新全量镜像实验，优先使用 QEMU snapshot、扇区 journal、稀疏/增量方案。
- 单个新文件超过 500 MiB 时，先说明理由、预计寿命和清理条件。
- 不保留无界日志、重复截图、重复工具链压缩包、`__pycache__` 或已经被新 manifest 取代的失败产物。

可使用下面的只读统计命令：

```powershell
$items = Get-ChildItem -Force -File -Recurse -ErrorAction SilentlyContinue
$bytes = ($items | Measure-Object Length -Sum).Sum
[pscustomobject]@{
  Files = $items.Count
  Bytes = [int64]$bytes
  GiB = [math]::Round($bytes / 1GB, 3)
}
```

## 3. 文档必须和成果同步

- 不要把发现只留在聊天、终端、截图或记忆里。每个有复用价值的成功、失败、排除项、文件哈希、地址、ABI 映射、导航坐标、测试结果和回滚方式，都要在进行下一项实验前写入相应 Markdown。
- 当前总交接文档是 `docs/22-current-project-handoff.md`；跨系统状态变化必须更新它。
- H2 使命结论更新 `systems/H2-2.X/docs/mission-feasibility.md`；构建/运行方式更新 `systems/H2-2.X/docs/reproduce.md`；目录/体积/删除更新 `docs/09-storage.md`。
- H1 V1→V2 使命更新 `docs/19-v1-v2-mission-handoff.md`；七游戏路径更新 `docs/20-v2-game-release.md`；飞天影音更新 `docs/21-v1-flying-video-port.md`。
- “静态覆盖”“成功启动”“可见菜单”“进入场景”“可玩”“实机验证”是不同等级，不能互相替代。

## 4. 模拟器进程纪律

- 启动前检查 8793、8796、8797 端口和现有进程。只结束能够确认属于本项目的旧 H1/H2 前端或 `qemu-system-mipsel.exe`；未知进程先报告，不盲目终止。
- Windows 后台启动必须使用隐藏窗口并记录 `Start-Process -PassThru` 返回的 PID。
- 第一阶段为了让我人工确认，可以同时保留三个模拟器；我确认后，不再需要的 H1 两个实例应及时停止，只保留 H2 研究实例。
- 每次测试结束后核对 QEMU、Python 前端、调试器、抓帧和辅助服务；不需要的全部结束。
- 浏览器页面关闭不等于后端结束，不要把关闭页面当作进程清理。

## 5. 模拟器操作路径与截图规则

- 对任何**新的或尚未验证的** UI 操作路径，先进行一次受限的截图勘察：只在关键页面转换后截图，确认页面、控件、坐标和激活方式。
- 不得反复截取相同画面，不得用大量截图代替对系统 UI 的理解。
- 路径一经确认，立即写成固定自动化脚本，至少包括：开机 readiness/指令进展检查、已知开机卡顿保护、固定坐标、触摸按下/释放时序、必要的硬件 Confirm/Return、超时、状态或 trace 验证以及单元测试。
- 后续运行必须用固定脚本，不再人工逐次点击；截图只用于脚本完成后的稀疏终态确认。
- 已经存在且已验证的路径直接复用，不重新截图摸索：
  - H1 V2 使命：`systems/2.X/tooling/navigate_h1_v2_mission.py`；
  - H1 V2 飞天影音：`systems/2.X/tooling/navigate_h1_v2_flying_video.py`；
  - H2 使命：`systems/H2-2.X/tooling/navigate_h2_mission.py`。
- H2 工具娱乐只有两页。右下箭头和使命图标都是“触摸选择，硬件确认激活”；不要恢复旧的三页判断或只触摸不确认的错误脚本。

## 6. Git、GitHub、隐私和网络

- 开始前运行 `git status --short --branch`、`git log -3 --oneline --decorate`、`git remote -v`。保护所有既存用户改动。
- 每个真实里程碑在同一轮更新源码、测试和文档，执行相关测试及 `git diff --check` 后提交。
- H1 1.X/2.X 的公共源码变化还要按 `docs/15-open-source-projects.md` 同步独立项目；H2 当前随 `bbk-h1-research` 管理。
- 推送后用远端引用确认 GitHub 已取得目标提交，不能只凭“push 命令无明显输出”宣布成功。
- GitHub 或下载网络直连失败时，使用本机 SOCKS5 代理 `127.0.0.1:45535`。优先使用命令级临时配置，不永久写入 Git 配置，也不记录凭据：

```powershell
git -c http.proxy=socks5h://127.0.0.1:45535 push origin main
git -c http.proxy=socks5h://127.0.0.1:45535 ls-remote origin refs/heads/main
```

- 其他命令需要代理时，只在当前进程临时设置 `ALL_PROXY=socks5h://127.0.0.1:45535`，完成后移除；不要把代理、用户名、主机路径或 token 写入项目文件。
- 每次发布或交接前运行 `python scripts/audit_release_secrets.py <target>`；必须审计最终 ZIP 本身。任何用户名、主机名、用户目录、Codex 配置路径、凭据、token 或私钥命中都是发布阻断项。
- 厂商固件、NAND/eMMC、商业 BDA、游戏数据、视频、IDA 数据库、运行日志和 sector journal 不进入 Git/GitHub。

# 第一阶段：读取资料与核验接管

## 1. 先读仓库规则

完整读取项目根目录 `AGENTS.md`。随后按顺序完整读取以下文件；不要只读标题或让子代理代读：

1. `docs/22-current-project-handoff.md`：当前总状态、活动镜像、回滚链和下一研究边界。
2. `docs/README.md`：文档索引。
3. `docs/09-storage.md`：当前 15 GiB 约束、清理记录和保留规则。
4. `docs/15-open-source-projects.md`：主仓库、H1 两个独立项目和发布边界。
5. `docs/16-v2-system.md`：H1 V2 系统、A/B FTL、模拟器和 ABI 证据。
6. `docs/19-v1-v2-mission-handoff.md`：H1 V1 使命→H1 V2 的已验证方法。
7. `docs/20-v2-game-release.md`：七款游戏的完整 A/B guest 路径。
8. `docs/21-v1-flying-video-port.md`：H1 2.X 飞天影音→H1 1.X。
9. `systems/H2-2.X/README.md`。
10. `systems/H2-2.X/docs/reproduce.md`。
11. `systems/H2-2.X/docs/mission-feasibility.md`。
12. `docs/02-ida-mcp.md`：确认当前会话是否真的暴露 IDA MCP；没有工具时不得假装已经使用。

然后阅读当前直接相关源码和测试：

- `systems/H2-2.X/mission/h2_mission_stage.c`
- `systems/H2-2.X/mission/h2_mission_entry_external.S`
- `systems/H2-2.X/tooling/build_h2_mission_loader.py`
- `systems/H2-2.X/tooling/install_h2_mission.py`
- `systems/H2-2.X/tooling/navigate_h2_mission.py`
- `systems/H2-2.X/tooling/test_navigate_h2_mission.py`
- `systems/H2-2.X/tooling/probe_h2_mission.py`
- `systems/H2-2.X/runtime/h2_emulator.py`

读取私有当前状态，但不要提交这些文件：

- `work/h2/s1-resource-test/install-s1-original-shellctx.json`
- `work/h2/s1-resource-test` 中当前活动的十二份撤销 journal；名单以 `docs/22-current-project-handoff.md` 为准。

## 2. 接管后必须能复述的事实

在启动模拟器前，用简短进度消息向我确认你理解以下边界：

- H1 V1.41、H1 V2.20 和 H2 V2.2L 是三套系统；H1 两代共用 H1 QEMU 技术栈，H2 使用独立 JZ4750L/H2 机器。
- 当前只保留 Windows ARM64 模拟器，不重建 x86 模拟器。
- H1 运行时固定 64 MiB；H2 固定 32 MiB。禁止为了让使命运行而提高 H2 RAM。
- H1 V1 使命→H1 V2 已由用户确认可玩；其他六款 V1 游戏只是结构/安装完成，尚未全部人工验收。
- H1 2.X 飞天影音→H1 V1.41 已在模拟器验证；V2 AVI 周期卡顿/片尾冻结的修复已经停止。
- H2 的 H1 V1 使命负载曾到菜单/剧情，但任务场景在 32 MiB 布局下发生真实堆分配失败。
- 当前 H2 活动分支必须使用 654,696 字节的**原版 S1 使命**，不得换成 9588 兼容 BDA，也不得偷偷换回 H1 使命负载。
- 当前 S1 负载已经到 `game-start`，H2 `GUI+0x980` 返回非零 shell handle `0x81229EC0`，但可见画面仍是词典；下一边界是 S1/H2 前台窗口 ABI，不是导航或 B 盘文件。

当前关键私有状态：

```text
H2 eMMC:
  emulator/h2/firmware/h2-v2.2l-emmc.raw
  SHA-256 F36A081422CFBC4C369652C93284A458842A4E421039ED5247A75A119786FC4C

H2 S1 wrapper:
  A:\应用\程序\中学时间.bda
  SHA-256 6E18730B7B1A316CEF296E6F1933F825966DA826AB932CE32BD8D3CEB0778485

S1 original payload:
  A:\V1GAME.BIN
  654,696 bytes
  SHA-256 C994ED436866FAC9BCC2AB88A5E1ECCAE6C4C33FC91A9C8CFBE9AA3E513262E7

S1 resources:
  B:\应用\数据\游戏\LYXZ\DataLib.dat
  SHA-256 8E8A5A4E7B45472841EA4839B5902726AEFE2F53DB7DE7B125CDB039A0CEB85D
  B:\应用\数据\游戏\LYXZ\DataLibIndex.dat
  SHA-256 D321227E79C628F167657F669F043BA230966E224D765C03332A720D6833EC59
```

不要一上来重新哈希所有大文件；先核对存在性、大小、manifest 和文档。只有发现异常或准备破坏性操作时才重新计算大镜像哈希。

# 第一阶段：启动三个模拟器并等待我确认

## 1. 启动前检查

1. 确认项目仍低于 15 GiB。
2. 查看 8793、8796、8797 是否监听，并检查占用 PID/命令行。
3. 确认以下文件存在：
   - `emulator/windows-arm64/firmware/h1-system.raw`
   - `work/v2-emulator/h1-v2-v1-games-b.raw`
   - `emulator/h2/firmware/h2-v2.2l-emmc.raw`
4. 不修改任何镜像，不进行新导航，不自动进入使命。

## 2. 使用实机等同设置启动

在项目根目录的 PowerShell 中启动。使用隐藏窗口并保存三个 `Start-Process` 返回对象/PID：

```powershell
$projectRoot = (Get-Location).Path

$h1v1Process = Start-Process -FilePath python -ArgumentList @(
  '-B', 'emulator/windows-arm64/h1_emulator.py',
  '--port', '8793',
  '--ram-mib', '64',
  '--no-browser'
) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

$h1v2Process = Start-Process -FilePath python -ArgumentList @(
  '-B', 'emulator/windows-arm64/h1_emulator.py',
  '--port', '8796',
  '--bootrom',
  '--touch-profile', 'v2',
  '--ram-mib', '64',
  '--nand', 'work/v2-emulator/h1-v2-v1-games-b.raw',
  '--no-browser'
) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

$h2Process = Start-Process -FilePath python -ArgumentList @(
  '-B', 'emulator/h2/h2_emulator.py',
  '--port', '8797',
  '--persistent',
  '--no-browser'
) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
```

不得给 H2 增加 RAM 参数，不得给 H1 使用 160 MiB。H1 V2 使用 snapshot/非 `--writable` 测试；H2 使用 `--persistent` 是为了保留当前活动实验状态。

等待三个 HTTP API 可用，读取 `/api/status`。至少确认：前端在运行、没有 `lastError`、QEMU 未退出、guest 指令/帧在合理时间内继续变化。不要用大量截图做健康检查。

## 3. 交给我浏览器确认，然后必须停下

三个模拟器健康后，给我以下地址：

- H1 V1.41：`http://127.0.0.1:8793/`
- H1 V2.20：`http://127.0.0.1:8796/`
- H2 V2.2L：`http://127.0.0.1:8797/`

说明三者当前各显示什么、是否有错误，并明确请求我人工确认。此时不要点击使命、不要运行 H2 导航、不要继续逆向、不要改代码。结束当前回合等待我的确认。

# 第二阶段：仅在我确认后继续 S1 使命→H2

## 1. 收拢进程和建立控制组

- 我确认三个模拟器正常后，停止不再需要的 H1 V1/H1 V2 QEMU 与前端，保留 H2 8797；如果需要对照 H1，只在采样窗口内重启，完成后立即结束。
- 记录本轮 H2 镜像摘要、manifest、Git HEAD、项目大小和进程 PID。
- 当前 H2 导航路径已经确认，直接运行 `systems/H2-2.X/tooling/navigate_h2_mission.py --url http://127.0.0.1:8797`，不要重新截图摸索。

## 2. 当前真正的逆向目标

不要再排查以下已经确认的内容：

- 不是点击到了错误的词典图标：stage trace 已进入精确 S1 负载。
- 不是 S1 数据没有放进 B：system/user FAT 已逐文件回读一致。
- 不是缺少 H2 shell：`GUI+0x980` 已返回 `0x81229EC0`，`+0x990` 关闭路径也已识别。
- `GUI+0x018` 是日志，不是应用注册。
- 不使用 9588 兼容 BDA 作为游戏负载。
- 不使用 H1 使命负载来替代当前 S1 目标。

优先研究：

1. S1 `GUI+0x084` 调用处构造的 320×240 窗口描述符布局和生命周期。
2. H2 当前映射目标 `GUI+0x07C` 的真实参数结构、返回对象、父 shell/owner 字段和前台注册语义。
3. H2 原生应用在 `GUI+0x980` 打开 shell 之后，创建首窗、激活、显示、焦点和合成前景的完整调用链。
4. 当前 `H2_KEEP_NATIVE_SCREEN=1` 与 S1 GUI 绘制路径之间的关系；先证明窗口所有权，再决定是否需要受控 LCD 模式切换。
5. 只有 S1 首窗真正可见后，才测量 S1 的堆峰值；当前没有证据说明 S1 已解决或仍触发 H1 分支的内存问题。

如果当前会话真正提供 IDA Pro MCP，按 `docs/02-ida-mcp.md` 检查连接后使用现有数据库做函数、交叉引用、结构体和调用约定分析。若没有 MCP，就使用已有报告、反汇编脚本和本地 IDA 状态；不得声称已经通过 IDA MCP 验证。

## 3. 每次实验的工程约束

- 一次只改变一个 ABI 假设。
- 从已知 wrapper 构建新文件，不手工不可复现地修改最终二进制。
- 构建器继续用尺寸和 SHA-256 fail-closed；S1 当前必须显式 `--variant s1-original`。
- 安装到 H2 前先生成新的唯一 manifest 和 sector journal；禁止覆盖现有文件。
- 安装后逐文件 FAT 回读并核对镜像前后摘要。
- 用固定导航和 trace 判定是否进入 payload，只在导航完成后截取最少终态图判断前台是否变化。
- 如果失败，记录“改变了什么、trace 到哪里、可见画面、已排除什么、如何回滚”，回滚或保留可逆层后再进行下一实验。
- 如果成功，立即更新文档、测试、Git 和 GitHub，再继续下一个问题。

# 第一条工作回报应该包含

完成资料读取和启动前检查后，先向我简短报告：

1. 当前 Git 状态以及你将保护的用户改动。
2. 当前项目大小与 15 GiB 余量。
3. 你对三个模拟器、两个 H2 使命分支和当前 S1 阻塞点的复述。
4. 即将启动的三个命令和端口。

随后启动三个模拟器、验证 API，给出三个浏览器地址，并停下来等我确认。不要越过这个停顿点。
````
