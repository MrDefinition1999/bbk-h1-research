# H1/H2 当前成果与 AI 续研交接

更新：2026-08-27（Asia/Irkutsk）

本文是当前工作区的总入口，供新的 AI 在不重复旧实验、不夸大验证状态的前提下继续研究。历史细节仍保留在各专题文档；如果专题文档与本文对“当前活动镜像”或“当前研究分支”的描述冲突，以本文和对应安装 manifest 为准。

## 1. 状态用语

- **已验证**：有动态运行、用户人工确认或逐字节回读证据。
- **结构完成**：构建、静态 ABI 覆盖和镜像安装校验已通过，但尚未完成实际玩法验收。
- **阶段性结果**：已经跨过若干关键边界，但还不能称为可玩或可发布成品。
- **未解决**：当前实验仍失败；必须如实保留失败表现和已排除原因。

## 2. 一页状态总览

| 项目 | 当前状态 | 最重要结论 |
| --- | --- | --- |
| H1 V1.41 模拟器 | **已验证** | Boot、完整桌面、触摸、键盘、音频、视频和原版使命均可运行；当前只保留 Windows ARM64 运行时。 |
| H1 V2.20 模拟器 | **已验证** | BootROM→Loader→U-Boot→OS→桌面完整链路可运行，使用与 V1 相同的 H1 QEMU 技术栈和 V2 触摸配置。 |
| H2 V2.2L 模拟器 | **已验证基础系统** | JZ4750L BootROM→MSC0/eMMC→H2L→系统→桌面可运行，固定 32 MiB RAM，端口 8797；使命仍未完成。 |
| H1 V1.41 使命→H1 V2.20 | **已验证可玩** | 通过 V2 原生 BDA 包装层、V1 ABI 兼容表和 B 盘资源映射运行；用户已实际进入并游玩。 |
| 其余六款 H1 V1.41 游戏→H1 V2.20 | **结构完成** | 106 个唯一服务调用全部覆盖，启动器/负载/资源逐文件校验通过；玩法、音频、存档和退出仍待逐款人工确认。 |
| H1 V2 飞天影音→H1 V1.41 | **模拟器内已验证** | 完整 2.X 播放器和 `player.bin` 已经由 V1 兼容层运行，普通 AVI 与加密 `EEBBKBMD` 视频均能解码、跳转和退出；实机仍待验收。 |
| H1 V1.41 两段 AVI→H1 V2 | **诊断已完成** | 两段原始 AVI 放到资源管理器可见的 B 盘后，原生 V2 播放器会周期卡顿并在自然播放结束后冻结，证明该现象不是使命移植专属问题；按用户要求不再修模拟器卡顿。 |
| H1 V1 使命负载→H2 | **历史阶段性结果** | 曾显示主菜单、创建角色和剧情；任务场景在 H2 实机等同的 32 MiB 布局中出现真实堆分配失败和花屏，不能称为可玩。 |
| S1 原版使命→H2 | **当前未解决** | 包装层已经加载精确 S1 原版负载，trace 到达 `game-start`，H2 原生 shell 句柄也创建成功，但可见前台仍是词典界面；问题已缩小到 H2 前台/窗口 ABI，而不是导航、文件缺失或模拟器重启。 |

## 3. 仓库与目录边界

主研究仓库为 `bbk-h1-research`，本地当前分支为 `main`，远端为：

```text
https://github.com/MrDefinition1999/bbk-h1-research.git
```

H1 两代系统已经拆成可以独立发布的源码树：

| 目录 | GitHub 项目 | 内容 |
| --- | --- | --- |
| `systems/1.X` | `bbk-h1-1x` | H1 V1.41 输入锁、NAND/FTL 工具、复现文档与 1.X 验证入口。 |
| `systems/2.X` | `bbk-h1-2x` | H1 V2.20 重建、V1 游戏兼容层、A/B 安装器与验证工具。 |
| `systems/H2-2.X` | 当前随 `bbk-h1-research` 管理 | H2 V2.2L 镜像工具、ARM64 模拟器、H2 专用使命 stage 与探针。 |

公共组件：

- `h1-bda-sdk`：MIPS BDA 构建、H1 服务表和 V1→V2 兼容 stage。
- `emulator/qemu/overlay`：H1/JZ4740 QEMU 机器与设备覆盖源码。
- `emulator/windows-arm64`：当前 H1 ARM64 运行目录。
- `emulator/h2`：当前 H2 ARM64 运行目录。
- `work/`：私有输入、NAND/eMMC、日志、逆向中间物和可恢复 journal；被 Git 忽略，不得发布。

已知的关键里程碑提交包括：

| 提交 | 内容 |
| --- | --- |
| `86d639a` | 拆分 H1 1.X/2.X 可复现项目。 |
| `c16021c` | 使命资源迁到原生 V2 B 卷并达到可玩。 |
| `a6dbfd0`、`55c0e15` | 固定使命导航、trace 安全区和默认站立回归。 |
| `54119fb` | 打包七款 V1 游戏兼容工程，并记录 AVI/模拟器问题。 |
| `17a8379` | 完整记录 H1 2.X 飞天影音→1.X 的移植。 |
| `eab496d` | 加入可复现的 H2 V2.2L 项目。 |

发布过的 H1 1.X/2.X 精确提交和源码 ZIP 摘要见 [15-open-source-projects.md](15-open-source-projects.md)。不要把 `work/` 中的商业 BDA、游戏数据、固件或镜像推送到上述仓库。

## 4. 当前本地模拟器布局

用户已经明确不再需要 x86 模拟器。当前本地运行时只有 Windows ARM64：

| 目标 | 前端 | 常用地址 | 真实设备约束 |
| --- | --- | --- | --- |
| H1 V1.41 | `emulator/windows-arm64/h1_emulator.py` | `http://127.0.0.1:8793/` | 64 MiB、单线程 TCG、不得通过宿主加速宣称实机性能。 |
| H1 V2.20 | 同一个 H1 前端，换 V2 NAND 并启用 `--bootrom --touch-profile v2` | `http://127.0.0.1:8796/` | 同为 H1 64 MiB；使命比较使用 `instruction_clock=false`。 |
| H2 V2.2L | `emulator/h2/h2_emulator.py` | `http://127.0.0.1:8797/` | 固定 32 MiB；不得为了跑使命虚增 RAM。 |

典型启动命令：

```powershell
# H1 V1.41
python -B emulator/windows-arm64/h1_emulator.py `
  --port 8793 --no-browser

# H1 V2.20 七游戏私有测试镜像
python -B emulator/windows-arm64/h1_emulator.py `
  --port 8796 --bootrom --touch-profile v2 --ram-mib 64 `
  --nand work/v2-emulator/h1-v2-v1-games-b.raw --no-browser

# H2 当前私有 eMMC；--persistent 会直接使用活动实验镜像
python -B emulator/h2/h2_emulator.py `
  --port 8797 --persistent --no-browser
```

H1 V1.41 默认本地 NAND 为 `emulator/windows-arm64/firmware/h1-system.raw`，大小 1,107,296,256 字节，当前 SHA-256 为 `614B0E5F85CA262A84BF26C7AD024043B32CE4CC6756D1C741E006846E134012`。H1 V2 私有测试镜像保存在 `work/v2-emulator`，没有复制到公开运行目录。

退出浏览器页面不会保证 QEMU/Python 一起结束。每次测试后必须核对并结束 `qemu-system-mipsel.exe` 和对应前端；本次交接前已停止 8797 的 H2 QEMU 与 Python 前端。

## 5. H1 V1.41 系统与模拟器

已完成的基础能力包括：

- JZ4740/XBurst、480×272 LCD、IPU、AIC、TCU、GPIO、SADC、MSC、NAND、UDC 和 H1 7×6 键盘矩阵的 H1 专用配置。
- 1 GiB NAND、JZ4740 ECC/OOB、128 页擦除块、H1 FTL 标签与完整 FAT16 系统卷重建。
- 首次启动四点校准、时间/容量提示、桌面、应用切换、触摸边缘坐标、网页画面/音频和完整键盘抽屉。
- 原版使命、原版游戏、普通 AVI、音频与飞天影音路径的动态运行。
- 实机性能比较时保持 64 MiB、单线程 TCG，不使用虚假超频。

原版使命是 H1 V1→V2 比较的控制组。默认站立动画 30 秒采样结果为 1.735 changed frames/s，P95 画面间隔 619.822 ms，音频 DMA 增量 323。详细硬件和模拟器历史见 [06-emulator.md](06-emulator.md)，V1 输入与运行状态见 [17-v1-validation.md](17-v1-validation.md)。

## 6. H1 V2.20 系统、A/B 分区与模拟器

V2 已经从官方 PC/SD 恢复包中完成容器、Loader、U-Boot、OS、ExtOs1/2 和 307 文件系统树的可复现提取。完整 BootROM 链和直接 OS 启动都已跑到桌面。

最容易重复犯错的是 A/B 存储模型：

- A 扫描物理块 `[120,1780)`，即工具中 `[0x40,0x6F4)`；系统、BDA 启动器和外部可执行负载放在隐藏 A。
- B 扫描物理块 `[1780,4096)`，即 `[0x6F4,0x1000)`；资源管理器只显示 B，原厂镜像没有 B 映射，因此首次看到空白 B 是正常行为。
- V2 原生 B FAT16 标签和几何为 `Y100 V2.2`；不能把 V1 FAT 几何直接扩到 V2。
- A 不能越过 `0x6F4` 扩容，否则与 B 扫描器冲突。
- 全局把系统里的 `A:` 改成 `B:` 会黑屏。正确方法是在特定游戏负载中只改已验证的资源路径驱动器字节。

详见 [16-v2-system.md](16-v2-system.md)。

## 7. H1 V1.41 使命移植到 H1 V2.20

### 7.1 为什么必须使用 V2 BDA 包装层

V1 应用入口为 `0x83C00020`，V2 应用有 64 字节前缀并从 `0x83C00040` 进入。V1 使命还调用 V2 中已移动、删去或改变语义的 GUI/资源服务，因此不能只改 BDA 头或文件名。

`h1-bda-sdk/examples/v2/v1_game_stage.c` 会：

1. 保留 V2 64 字节原生前缀；
2. 建立 V1 形状的 GUI/FS/SYS/MEM/RES 服务表；
3. 在 `0x83C00020` 执行未改代码布局的 V1 游戏负载；
4. 在退出时恢复 V2 前缀和状态。

七款 V1.41 游戏共使用 120 个服务槽：21 个直接转发、88 个 GUI 重定位和 11 个本地兼容 shim。关键映射包括 `GUI+0x6E0→V2 GUI+0x9E4`、`GUI+0x72C→V2 GUI+0x688`、`GUI+0x84C` 状态桥、允许但不扣币的 `GUI+0xAA4/+0xAA8`，以及 `RES+0x094` 返回零 shim。

### 7.2 最终文件布局

- 启动器：`A:\应用\程序\中学时间.bda`。图标/标题显示使命，但仍占用原生“中学时间”的文件槽。
- 外部负载：`A:\V1GAME.BIN`。
- 大资源：`B:\应用\数据\游戏\LYXZ\DataLib.dat` 与 `B:\应用\数据\游戏\LYXZ\DataLibIndex.dat`。
- 使命负载中恰好五个私有 `A:\应用\数据\游戏\` 前缀只改驱动器字节为 B；其他系统路径不变。

### 7.3 动态结论

2026-08-18 用户人工确认第一个使命入口能正常进入并游玩。另两个旧实验入口分别是“缺少使命数据”和死机，后来已恢复为原生 V2 应用，不能再把那两个入口当测试目标。

安全 wrapper 的 trace 从冲突的 `0x83E00B00` 移到保留 stage 区 `0x83F0E000`。已部署 wrapper SHA-256 为 `154B601539E1B865A08D658B2C2038093C5BCA4E1C34935183977B5008E93C2C`。最终使命+B 私有镜像为：

```text
work/v2-emulator/h1-v2-mission-b.raw
bytes:   1,107,296,256
SHA-256: 535D373C6DAEC12654C7611B81064AC2C64E1F742C9B4BFF0C6E67BC39A89C8F
```

默认站立动画的可复现 A/B 对比中，V2 changed frames/s 为 1.739，V1 为 1.735，差异 +0.23%；P95 只差 4.373 ms，没有约一秒的指令塌陷。手动跑动时看到的周期卡顿后来也在原生 V2 AVI 播放中复现，因此不应再归因于使命兼容层。

固定导航工具为 `systems/2.X/tooling/navigate_h1_v2_mission.py`。它清理恢复态，进入“其他→工具娱乐”，用页面箭头到第二页，点最后一个使命图标并发送硬件确认，然后通过 stage trace 验证新一代 `GAME_START/GAME_RETURN`；不要恢复为截图识别或人工点击脚本。

完整原理和路径分别见 [19-v1-v2-mission-handoff.md](19-v1-v2-mission-handoff.md) 与 [20-v2-game-release.md](20-v2-game-release.md)。

## 8. 其余六款 V1 游戏移植到 H1 V2

`install_h1_v2_v1_game_suite.py` 已把同一兼容 stage 特化给中国象棋、俄罗斯、宠物泡泡、猫狗大战、雷霆战机和黑白子。它只改外部负载路径、长度和缓存终点，并对每款游戏执行固定数量的 A→B 资源路径改写。

完整 guest 路径以 [20-v2-game-release.md](20-v2-game-release.md) 为准。最终私有验证镜像：

```text
work/v2-emulator/h1-v2-v1-games-b.raw
bytes:   1,107,296,256
SHA-256: 7CDBA2CA81CB3E252752C39F70642FBA8648AB8CBC3F2409B241BF3C1EA0D031
```

已验证：106 个唯一服务调用全部有兼容规则，启动器、外部负载和 16 个资源文件均通过 FAT/FTL 逐字节回读，且 A/B 写入窗口互不越界。

未验证：六款游戏的实际启动、完整玩法、音频、正常退出及宠物泡泡存档。新的 AI 必须逐款记录，不能用“静态覆盖为零”代替动态可玩结论。

## 9. 飞天影音的两项不同成果

### 9.1 H1 2.X 播放器移植到 H1 1.41

这是完整应用移植，不是只复制视频。2.X 播放器负载从 `0x83C00040` 适配到 V1 的 `0x83C00020`，兼容表位于 `0x83F40000` 以上。2.X UI/解码资源独立安装为 `A:\应用\数据\play2.bin`，避免覆盖 V1 共用的 `player.bin`；媒体根从 `B:\多媒体\飞天影音\` 重定向到 V1 可见的 `A:\飞天影音\`。

生成 BDA 为 3,442,856 字节，SHA-256 `753ED2D6EFF71BC51714C11A37EF34AEA1CB8DFBF225497B17835D76C86484A0`。在 H1 V1.41 ARM64 模拟器、真实 64 MiB、单线程 TCG 下已经验证：

- 普通 DX50/MPEG-4 AVI 能输出 44.1 kHz 音频，跳到 00:29 后出画面并正常退出；
- 原始 32,587,009 字节 H2 `EEBBKBMD` 样片被识别为 13:29，能解密 MP3 音频并在 02:10 显示 480×270 FMP4 画面；
- seek 和关闭路径不再破坏应用，能回到 V1 桌面。

00:00 可能长时间黑屏是模拟器中的解码预滚，不等于解密失败；测试应跳到非零时间。实体 H1 尚待验收。全部细节见 [21-v1-flying-video-port.md](21-v1-flying-video-port.md)。

### 9.2 V1.41 两段 AVI 放入 V2 B 盘

V1.41 的 `飞天影音` 根目录有两段原始 AVI：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `@ibox学习机广告.avi` | 8,496,944 | `0F74E1E937F1E640B14BC1D87BC2D290DA9A386B94D85818C98935E23A697BDF` |
| `拜见罗宾逊一家(meet the robinsons).avi` | 14,987,940 | `9556748647CBBE90B6E118750D3E60ADDDED78EB534FD53925105B6B69048A2E` |

`install_h1_v2_flying_video_samples.py` 会原样放到 `B:\飞天影音`，保留原生 V2 `飞天影音.bda`，并证明 A 未改变。资源管理器隐藏 A，因此早期放 A 的测试无效。

用户确认 V2 原生播放器周期暂停，并在视频自然结束后整个 guest 冻结。ARM64 原生 QEMU、时钟设置和 AIC 边界实验均未解决；其中恢复旧 AIC 排空行为会产生大量 underrun 和 reserved-instruction 停滞，已经回退。按用户要求，不再继续模拟器卡顿修复。

固定导航为 `systems/2.X/tooling/navigate_h1_v2_flying_video.py`：打开飞天影音→点下方第一个按钮→等待自动搜索 B→勾选第一项前的框→点内部可靠“打开”坐标。不要用反复截图猜路径。

## 10. H2 V2.2L 模拟器

H2 项目保持与 H1 类似的“QEMU + Python HTTP/Web 前端”技术栈，但机器模型和固件完全独立：

- 机器：`bbk_iboxh2`，JZ4750L。
- 内存：32 MiB SDRAM，超过范围会回绕；模拟器不可加 RAM。
- 显示：480×272。
- 存储：MSC0/eMMC，2 GiB 私有镜像。
- 输入：H2 七个 GPIO 键和 H2 SADC 触摸，不虚构 H1 全键盘或联机芯片。
- 启动链：BootROM→MSC0/eMMC→H2L→系统→桌面，已动态验证。

OpenNoah H2 QEMU 未完整实现 JZ4750L 从 `WAIT` 唤醒，原系统约一分钟后可能停在 `0x804C49BC`。`patch_h2_simulator_idle.py` 只对模拟器镜像中的两份系统副本做可逆 WAIT→NOP，并保留撤销记录；实机镜像不需要也不应使用这个补丁。

H2 基础镜像的可复现构建和 614 个 packet 文件校验见 `systems/H2-2.X/docs/reproduce.md`。原始干净构建摘要为 `7B44B5403EFBB58E6D34F676DE81D251DA6ABF9E0D1502D900E3012759DE40C7`；使命实验叠加后的当前活动镜像见第 12 节。

## 11. H1 V1 使命负载移植 H2：历史分支

2026-08-26 的 H1 V1 负载分支已经验证 H2 专用 stage 可以完成：

- H2 原生 BDA 前缀 `0x81C30000`/入口 `0x81C30040` 到 V1 游戏 `0x83C00020` 的桥接；
- H2 堆记录区迁移、V1 服务表、H2 消息泵和七键上下文映射；
- LCD 32 位 BGRA 接管及返回后 RGB565 恢复；
- 从 H2 FAT 逐字节读回 wrapper、负载和两份 DataLib；
- 显示使命主菜单、创建角色和剧情。

但进入“光明城”任务场景后显示不完整。动态断点在 H2 分配器 `0x80025868` 命中真实失败分支，请求 216 字节时返回空指针。主堆测量为：

| 时点 | 堆容量 | 存活分配 | 最大连续可申请 |
| --- | ---: | ---: | ---: |
| H1 1.X 使命任务场景 | 32.000 MiB | 20.023 MiB | 10.408 MiB |
| H2 启动使命前 | 18.266 MiB | 8.044 MiB | 10.023 MiB |
| H2 使命主菜单 | 18.078 MiB | 12.275 MiB | 5.434 MiB |
| H2 异常任务场景 | 18.078 MiB | 17.337 MiB | 0.366 MiB |

所以结论不是“使命必须有 64 MiB”，而是当前 H2 布局只给系统主堆留下约 18.08 MiB，并在场景切换瞬时峰值失败。这个历史结果仍有效，但当前活动镜像已经改成 S1 原版实验，不能拿当前镜像复现上述菜单/剧情画面而不先回滚或重建。

## 12. S1 原版使命移植 H2：当前活动分支

用户明确要求停止使用 9588 兼容 BDA，也不要再换回导致花屏的 H1 负载；当前目标是 `BBK9588-shiming` 项目中备份的**原版 S1 使命 BDA**。9588 兼容版只可作为 ABI/字体实现参考，不得再作为 H2 的游戏负载。

### 12.1 当前安装内容

当前 `emulator/h2/firmware/h2-v2.2l-emmc.raw`：

```text
bytes:   2,147,483,648
SHA-256: F36A081422CFBC4C369652C93284A458842A4E421039ED5247A75A119786FC4C
```

最后一层 manifest 为 `work/h2/s1-resource-test/install-s1-original-shellctx.json`，安装内容为：

| 内容 | guest 路径 | 字节数 | SHA-256 |
| --- | --- | ---: | --- |
| H2 包装启动器 | `A:\应用\程序\中学时间.bda` | 15,484 | `6E18730B7B1A316CEF296E6F1933F825966DA826AB932CE32BD8D3CEB0778485` |
| S1 原版使命负载 | `A:\V1GAME.BIN` | 654,696 | `C994ED436866FAC9BCC2AB88A5E1ECCAE6C4C33FC91A9C8CFBE9AA3E513262E7` |
| S1 `DataLib.dat` | `B:\应用\数据\游戏\LYXZ\DataLib.dat` | 88,846,119 | `8E8A5A4E7B45472841EA4839B5902726AEFE2F53DB7DE7B125CDB039A0CEB85D` |
| S1 `DataLibIndex.dat` | `B:\应用\数据\游戏\LYXZ\DataLibIndex.dat` | 180,216 | `D321227E79C628F167657F669F043BA230966E224D765C03332A720D6833EC59` |

安装器已从 H2 system/user FAT 逐文件回读一致；所以当前失败不是“数据没有放进 B 盘”。

### 12.2 已经确认的 S1/H2 ABI 事实

- `build_h2_mission_loader.py` 现在严格支持 `h1-v1`、`s1-9588` 和 `s1-original` 三种已知哈希/尺寸；当前必须选择 `--variant s1-original`。
- S1 与 H1 V1 共享较老的 GUI 布局，但多个服务相对 H2 有固定偏移，已加入 S1 专用映射和最小 shim。
- 对 H2 原生 60 个 BDA 的扫描表明，它们都会先调用 `GUI+0x980` 打开 `A:\系统\数据\shell\*.dlx`，结束时调用 `GUI+0x990` 关闭。`GUI+0x18` 只是日志，不是应用注册服务。
- 当前 wrapper 复用原生时间应用的 `A:\系统\数据\shell\TIME_Z.dlx`。最新 trace 中 H2 返回非零 shell handle `0x81229EC0`，因此“没有 H2 shell 上下文”已排除。
- 固定导航启动了精确的 654,696 字节 S1 原版负载，stage 到达 `game-start`；QEMU 未崩溃、未重启，系统也没有跳入异常重启画面。

### 12.3 当前失败表现与下一边界

尽管游戏代码仍在运行，最终可见画面仍是正常词典 UI。这里的正确解释是：外来 S1 BDA 没有取得 H2 的前台/窗口所有权，旧词典窗口继续被合成；不能解释为“移植失败就自动回到词典”，也不能归因于点击了错误词典图标，因为 trace 已确认进入了使命负载。

最值得继续逆向的边界是 S1 `GUI+0x084`。S1 调用处构造的是 320×240 窗口描述符；当前把它桥到 H2 `GUI+0x07C` 虽能创建对象，但两代结构/语义可能并不兼容。应先对比 S1 原生 `+0x084`、H2 原生应用首窗创建链和窗口前台注册流程，再扩大兼容层。不要再次从导航或数据文件开始排查。

S1 负载的实际 RAM 峰值尚未得到动态数据。它可能比 H1 版本更小，但当前失败发生在可见首窗之前，不能据此宣布 32 MiB 内存问题已经解决。

### 12.4 精确回滚

当前最后一层可用以下 journal 恢复到 SHA-256 `F60285BAE3081B2A694637F8EB63536D0A102080F8666E43BCECBC93951E7CAB`：

```text
work/h2/s1-resource-test/undo-s1-original-shellctx.sectors.gz
```

完整活动链需要按“从新到旧”逐层撤销，不能跳层。临时 H1 负载分支已经通过 `undo-h1v1-current.sectors.gz` 撤销；该 journal 不属于下面的活动链，并已在 2026-08-27 清理时移入回收站，不能再次应用：

| 当前摘要前缀 | 使用 journal 后恢复到 |
| --- | --- |
| `F36A0814` | `undo-s1-original-shellctx.sectors.gz` → `F60285BA` |
| `F60285BA` | `undo-s1-original-current.sectors.gz` → `DEE9326B` |
| `DEE9326B` | `undo-s1-9588-native7e0.sectors.gz` → `91492B08` |
| `91492B08` | `undo-s1-9588-trace.sectors.gz` → `2C58E4DA` |
| `2C58E4DA` | `undo-s1-9588-map.sectors.gz` → `59F2F388` |
| `59F2F388` | `undo-s1-original-map.sectors.gz` → `B8EC46F1` |
| `B8EC46F1` | `undo-s1-original-shim.sectors.gz` → `8C0F992C` |
| `8C0F992C` | `undo-s1-original-layout.sectors.gz` → `5EAEA369` |
| `5EAEA369` | `undo-s1-original.sectors.gz` → `3D3EA803` |
| `3D3EA803` | `undo-s1-rgb.sectors.gz` → `CB91E458` |
| `CB91E458` | `undo-s1-bda.sectors.gz` → `36D853B6` |
| `36D853B6` | `undo.sectors.gz` → `8BBAC8AF` |

所有 journal 和 manifest 都在 `work/h2/s1-resource-test`，属于私有本地恢复资料，不进入 Git。更稳妥的干净复现方式仍是从官方输入重建 2 GiB 基础镜像，再只应用目标安装层。

## 13. H2 固定导航：不要再重复人工/截图试错

H2 开机后桌面会短暂可见，但触摸调度仍可能阻塞约 5 秒。导航脚本会等待运行时 uptime 至少 35 秒，再额外等待 6 秒。正确的工具娱乐页只有**两页**：

1. 发送 5 次返回，归一化任何恢复的应用/嵌套页面；
2. 点“更多功能” `(420,258)`；
3. 先点相邻分类 `(380,258)`、`(390,258)`；
4. 再点“工具娱乐” `(430,258)`、`(440,258)`；
5. 点一次右下页箭头 `(455,216)`，然后发送硬件确认；触摸只选择箭头，确认才切页；
6. 第二页最后一个时钟图标 `(402,61)` 是使命测试槽；触摸选择后再发硬件确认；
7. 读取 stage trace，要求 generation 改变且 phase 为 `game-start` 或 `game-return`。

执行：

```powershell
python systems/H2-2.X/tooling/navigate_h2_mission.py `
  --url http://127.0.0.1:8797
```

这个脚本不读取截图。可以在脚本结束后只截一张终态图检查显示，但不能用大量截图来控制导航。旧的“三页工具娱乐”判断、只点箭头不确认、开机 5 秒内立即点击和把第一个词典/时间图标当使命，都是已确认的错误路径。

## 14. 已知模拟器问题与暂停范围

- H1 V2 视频会周期卡顿并在自然播放结束时冻结；与使命跑动时的主观现象相似。修复工作已经按用户要求停止。
- H1 BootROM 偶发在“请重新设置时间”画面附近进入 reserved-instruction 循环；此时后端输入计数增加但 guest 指令不前进，不是按键映射错误。`prepare_h1_v2_desktop.py` 会检查指令进展并最多固定重试三次。
- H2 OpenNoah QEMU 的 WAIT 唤醒缺失由模拟器专用、可逆镜像补丁规避；这不是实机补丁。
- H2 当前 S1 使命显示失败属于应用前台/窗口 ABI，不能靠提高 RAM、反复点击或替换为 H1 负载掩盖。

## 15. 接手时先做什么

如果继续 H2 S1 使命：

1. 先读本文、`systems/H2-2.X/docs/mission-feasibility.md`、当前 stage 源码和最后一层 manifest。
2. 保持当前 S1 原版负载与 B 盘资源，不再使用 9588 兼容 BDA 作为负载。
3. 使用固定导航脚本和 trace，只在到达使命后做稀疏终态截图。
4. 对比 S1 `GUI+0x084` 320×240 描述符、H2 `GUI+0x07C` 和 H2 原生 `GUI+0x980/+0x990` shell/首窗流程。
5. 每次只改变一个 ABI 假设，生成独立 wrapper、manifest 和可逆 sector journal。
6. 在 S1 首窗真正可见后再测 RAM；在此之前不要把显示失败写成内存不足。

如果验收 H1 V2 六款游戏：

1. 启动 `h1-v2-v1-games-b.raw`，保持 64 MiB、单线程 TCG和实机等同设置。
2. 逐款记录启动、玩法、音频、退出、存档/读档。
3. 只把用户实际确认的项目升级为“已验证”；同步更新 [20-v2-game-release.md](20-v2-game-release.md)、Git 和对应 GitHub 项目。

## 16. 测试、隐私和清理纪律

当前 H2 导航最小回归：

```powershell
python -m unittest systems/H2-2.X/tooling/test_navigate_h2_mission.py -v
```

发布前必须：

1. 只从 tracked source 构建源码归档；
2. 不包含用户名、主机名、用户目录、Codex 配置、凭据、token、私钥、固件、NAND/eMMC、商业 BDA/游戏/视频、IDA 数据库、日志或截图；
3. 对源码树和最终 ZIP 本身运行 `python scripts/audit_release_secrets.py <target>`；任何命中都阻断发布；
4. MIPS/原生二进制尽量做路径前缀映射并剥离发布符号；
5. 删除或回收 `__pycache__`、编译缓存、失败截图和已被新 manifest 取代的临时文件，但保留当前镜像所需的撤销 journal；
6. 不修改、提交或覆盖与本任务无关的用户工作。交接时 `scripts/qemu_gdb_read.py` 有一份既存用户改动，应继续排除在本轮提交之外。
7. 整个项目目录当前硬上限为 20 GiB，19.5 GiB 预警；开始和结束时统计体积，预计达到上限前先安全清理或向用户确认。

用户已确认本机安装了 IDA Pro。涉及固件、BDA、ABI、函数、结构体或汇编行为的逆向工作，必须先按 [02-ida-mcp.md](02-ida-mcp.md) 验证 IDA Pro MCP/`idalib-mcp` 可正常执行只读分析，并在需要逆向时始终使用它取得直接证据。若工具或技能不可用，先参考 <https://github.com/mrexodia/ida-pro-mcp> 修复、重启并重新验证，不得静默降级为仅凭旧报告或文本反汇编继续猜测。

当前工作区仍有体积较大的私有必要项：H2 2 GiB 活动 eMMC、H1 V1/V2 约 1.1 GiB 的基准/测试 NAND、H2 Zig 工具链、S1/H1 使命资源和撤销日志。只有在确认能从锁定输入重建、结论已写入文档且当前回滚链不再依赖后，才可以通过可恢复方式清理。

## 17. 进一步阅读顺序

1. 本文：当前跨机型总览和活动实验状态。
2. [15-open-source-projects.md](15-open-source-projects.md)：公开仓库与发布边界。
3. [16-v2-system.md](16-v2-system.md)：H1 V2 系统、A/B、模拟器和兼容层证据。
4. [19-v1-v2-mission-handoff.md](19-v1-v2-mission-handoff.md)：H1 V1 游戏→H1 V2 的 ABI 和使命动态结果。
5. [20-v2-game-release.md](20-v2-game-release.md)：七款游戏的完整 A/B guest 路径。
6. [21-v1-flying-video-port.md](21-v1-flying-video-port.md)：H1 2.X 飞天影音→1.X。
7. `systems/H2-2.X/docs/reproduce.md`：H2 构建、运行和安装。
8. `systems/H2-2.X/docs/mission-feasibility.md`：H2 使命两条分支的技术细节。
9. [23-next-ai-start-prompt.md](23-next-ai-start-prompt.md)：下一位 AI 的可复制启动提示词，包含三模拟器人工确认停顿点和后续 S1 续研约束。
