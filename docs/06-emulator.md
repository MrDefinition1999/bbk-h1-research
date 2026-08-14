# H1 QEMU 模拟器

最后更新：2026-07-23（Asia/Irkutsk）

本文持续记录 H1 模拟器的实现与实机固件验证结果。除非明确标为
**推断**或*待确认*，结论均来自 H1 V1.41 固件、可重复脚本或实际 QEMU
运行。

最终发行目标为 **Windows x86-64（Intel/AMD PC）**。本文中的原生 ARM64
构建用于前期在当前 ARM64 Windows 开发主机上执行固件验收；最终 x86-64 构建
也已在 Windows-on-Arm 的 x64 转译层完成全系统回归。FAT/FTL 镜像、H1 machine
源码和运行参数不依赖宿主架构。32 位 x86 Windows 不属于默认目标。

## 实现基线

模拟器基于 QEMU 11.0.0 和 `bbk9588-emulator` 的 JZ4740 外设模型开发。
H1 的源码 overlay 位于 `emulator/qemu/overlay/`，安装脚本为
`emulator/qemu/scripts/install_qemu_overlay.py`。参考仓库
`references/bbk9588-emulator/` 保持原样，便于持续比较上游实现。

官方 `bbk9588-emulator` v0.1.6 Windows 发布包曾下载并验证，SHA-256 为：

```text
8E87E0282C3BEC0186390D20446F8E0A4D5C364EA9D26F558BBF059C3798C16B
```

该哈希与 GitHub release 一致。QEMU 11.0.0 源码包的 SHA-256 为：

```text
C04CA36012653F32D11C674D370CF52A710E7D3F18C2D8B63E4932052A4854D6
```

两份下载归档在成功解压后已按 `docs/09-storage.md` 的保留策略删除；验证哈希
保留在本文，需要时可重新下载。当前源码树 `work/tools/qemu-11.0.0/` 已确认包含 `configure`、顶层
`meson.build`、`hw/mips/meson.build`，并含 78,380 个普通文件。Windows
`tar.exe` 对 ROM 子模块中的符号链接曾报告错误，但核心 QEMU 源码满足下一步
配置检查；若构建发现缺失文件，再使用 MSYS2 `tar` 重解到短路径。

## H1 machine 与 9588 的差异

新增的 QEMU machine 名称为 `bbkh1`，继承现有 `bbk9588` machine 的 JZ4740
外设框架，但覆盖下列板级参数：

| 项目 | H1 | 9588 基线 |
| --- | ---: | ---: |
| SDRAM | 64 MiB | 160 MiB |
| LCD | 480 x 272 | 240 x 320 |
| framebuffer | 4 bytes/pixel | 2 bytes/pixel |
| raw frame 大小 | 522,240 bytes | 153,600 bytes |
| NAND pages/block | 128 | 64 |
| SPI/SSI | `0xB0043000`，IRQ 16 | 原模型未实现 H1 路径 |

状态：H1 参数由固件逆向确认；machine 源码、原生 ARM64 构建和启动验收均已完成。
H1 不实例化 9588 专用的 panel/status 设备。host framebuffer bridge 已改为
运行时配置宽、高、stride、每像素字节数，并支持 RGB565 与 XRGB8888。

NAND 模型新增 `pages-per-block` 属性，program/erase 均使用实例值；H1 设置为
128，9588 保持 64。新增的 JZ4740 SSI 模型当前提供轮询模式所需的空闲、发送
就绪和接收空状态，外接 SPI 器件的身份仍*待确认*。

## 未修改 9588 二进制的基线运行

为排除 H1 machine 自身改动的影响，已先用未修改的 v0.1.6
`qemu-system-mipsel.exe` 直接加载 H1 `project.bin`。测试副本位于
`work/emulator/project.bin`，SHA-256 为：

```text
D05786E442F9AAD62A8D0A0CB4F6D786BDC7C2FA353A7A2B152C9ED9F01B40EF
```

基线运行已确认：

1. raw 镜像被装载到 `0x80004000`；
2. 成功进入 C 入口 `0x80004B60`；
3. 完成 BSS 清零、异常向量安装和 cache 初始化；
4. 进入 `0x800046F4`，开始初始化 176 项中断处理表；
5. 在 `0x80004514..0x80004548` 首次读写 DMAC channel 窗口后，x64 QEMU
   在 ARM64 Windows 上以 `0xC00000FF` 退出，尚未执行 UART 初始化，因此
   尚未输出 `start Y100`。

相关执行日志为 `work/emulator/baseline-in-asm.log` 和
`work/emulator/baseline-160m.log`。固件按
`0xB301FC14 + irq * 0x20` 计算寄存器地址：IRQ 32 对应 DMAC channel 0 的
`0xB3020014`，IRQ 38 会对应 offset `0xD4`。现有 9588 DMAC 模型只定义 6 个
channel。IDA 对 `0x80004480` 的反编译确认 IRQ 32..38 都走这条通用禁用路径。
同时，v0.1.6 源码确认 DMAC 对外公开 64 KiB MMIO window，`0xD4` 仍在数组内；
第七个 stride 只作为无语义的保留 shadow 读写，不会造成模型数组越界。因此它
**不能解释**基线进程退出，也不能作为把真实 DMAC 扩为 7 通道的依据。

自编译 x64 QEMU 精确复现了同一退出点；Windows SDK 头文件确认
`0xC00000FF` 是 `STATUS_BAD_FUNCTION_TABLE`。换用原生 ARM64 QEMU 后，该异常
完全消失，固件能稳定越过首次 DMAC MMIO。因此该退出已确认为 **ARM64 Windows
运行 x64 TCG 动态代码时的宿主兼容性问题**，不是 H1 固件或 DMAC channel 数量
导致的 guest 异常。

原生 ARM64 的第一次 15 秒探针记录于
`work/emulator/h1-arm64-direct-run1-{uart,qemu,stderr}.log`。已确认：

1. QEMU 持续运行到探针超时，没有宿主崩溃；
2. 固件执行了 `0x80004E9C..0x80004F0C` 的 UART0 初始化；
3. 随后执行了多个后续初始化入口；
4. `in_asm` 日志中新出现的最后一组翻译块为 `0x8004786C..0x80047878`，其代码
   轮询 DMAC channel 5 的 DTC (`0xB30200A8`)。这里记录的是“最后一次新翻译的
   basic block”，不是足以单独证明 CPU 最终停点的执行 trace；
5. 对该通道增加 address-error 快照后，确认固件写入的状态为：

   ```text
   DSA=0x01C04900 DTA=0x18000000 DTC=0x20 DRT=8
   DCS=0x80000001 DCM=0x00C01300 DMACR=0x00000301
   ```

   `0x18000000` 是 CPU KSEG1 `0xB8000000` 对应的 NAND data aperture。旧模型
   强制 AUTO DMA 的源和目标都位于 SDRAM，因而把合法的 NAND MMIO 目标误报为
   address error；这才是 DTC 未归零的直接原因。

修复后，AUTO DMA 通过 QEMU 系统物理地址空间执行每次总线事务，并依据 DCM 的
源/目标端口宽度拆分访问。`DCM=0x00C01300` 表示源/目标递增、16-byte 传输单位、
32-bit 源端口和 8-bit 目标端口。NAND aperture 同时改为按 A16/A15 解码
address/command/data，data 区低地址位被忽略，因此递增的 8-bit DMA 写会持续落到
NAND data port，而不会只接受精确的 offset 0。

修复后的两次实机探针为：

1. 默认 `bbkh1` 在约 5 秒后由固件写 RTC `HCR.PD`，QEMU 以 guest shutdown
   正常退出，记录于 `work/emulator/h1-arm64-dmac-fixed1-*`；
2. 使用 `bbkh1,hibernate-poweroff=off` 后持续运行满 15 秒，固件最终进入
   `0x80031798` 的休眠死循环，记录于
   `work/emulator/h1-arm64-dmac-fixed2-no-poweroff-*`；
3. 两次日志均无 DMAC address error、guest error 或 unimplemented MMIO，说明
   channel 5 的 DTC 已完成并且固件已越过原轮询；
4. 当前未提供 NAND 镜像，固件在完成后续初始化后主动休眠。因此下一里程碑是装入
   含 H1 系统数据的 raw NAND，而不是继续放宽 RTC 休眠语义。

UART 日志仍为空，故 `start Y100` 不能作为 UART 输出里程碑。IDA 已确认
`0x80004C88` 是无条件返回 0 的可变参数 stub；固件只是把该字符串传入 stub，
不会执行 UART 写入。现有运行结果确认 UART0 初始化代码被执行，空日志是预期行为。

## raw NAND、FTL 与首个 LCD 画面

恢复程序的 boot-area 布局已被编码为
`work/emulator/h1-boot-nand.raw`，但该中间镜像只有 62 个物理块。模拟器默认
NAND ID 为 `EC DC 10 95 44`，其中 device ID `0xDC` 对应 512 MiB、2,048 个
128-page erase block。用 62-block backing 启动时，固件不会休眠，而是在
`0x8004927C` 的 FTL 初始化中持续分配块、写入元数据；运行中 `s6` 在 5 秒内从
`0x2640` 增至 `0x2980`，确认它在前进而不是停在固定 PC。越过 backing 末尾后，
NAND 模型返回 program fail，固件按每块三次重试并标坏，因此这种容量不一致的
镜像不能作为完整设备运行。

与 ID 匹配的完整 backing 曾生成为：

```text
work/emulator/h1-512m-nand.raw
raw bytes: 553,648,128
physical blocks: 2,048
SHA-256: F416A5D33C5A1D9E5222BD106BF896F0CE8183C1AC4DDF03CADF79579913F2F2
```

该 512 MiB backing 及 guest 写入后的副本在 FTL 格式确认后已删除，可用
`scripts/make_h1_nand.py` 和本节参数重建；清单、哈希、日志与截图均保留。

使用完整 backing 的 15 秒探针记录于
`work/emulator/h1-arm64-512m-nand1-*`。已确认固件越过 NAND/FTL 初始化，进入
`0x8003EExx..0x8003FFxx` 的上层界面绘制和持续事件循环；日志包含 3,001 个新
翻译块，无 guest error、unimplemented MMIO 或休眠路径。运行中断点快照为正常
中断入口 `PC=0x80000180`、`EPC=0x800075E0`，后者位于输入/事件轮询代码。

QEMU monitor 导出的首张画面为 480x272：

```text
work/emulator/h1-512m-screen1.png
background #000060: 130,507 pixels
cursor #68B0F0: 53 pixels
unique colors: 2
PNG SHA-256: 028C1187426022D2DE96EF84CBA5DFE0445393597960A4E0E83BB6903A651B45
```

状态：**LCDC DMA、480x272 分辨率、像素转换和非黑屏已确认**。当前只有深蓝背景
和左上角十字光标，说明上层运行时已经启动，但 482 个 `系统数据` 文件尚未构造成
BBK FTL 卷；完整桌面/菜单显示仍依赖下一阶段的 FTL 格式逆向与卷注入。

## 当前实现风险

- 9588 专用 panel bridge 和 H1 SSI 都使用物理地址 `0x10043000`（KSEG1
  `0xB0043000`），但 machine 初始化已按型号互斥实例化二者，因此不存在 MMIO
  重叠。CIM 是独立的 `0xB3060000` 外设。该项经 board 源码复核为**确认**。
- DMAC 模型公开 64 KiB MMIO 窗口，语义上仅接受 channel 0..5。H1 的中断表
  初始化会访问第七个 stride 对应的保留 shadow；当前保持 JZ4740 的 6 个真实
  channel，等待后续 DMA 初始化代码或实机资料证明是否存在其他控制器。
- UART0 初始化、LCDC DMA 和 480x272 非黑屏已完成验证。后续依次验证 BBK FTL
  系统卷、完整桌面与菜单、按键、SD 文件系统、音频和 USB。

## 构建状态

便携 MSYS2 位于 `work/tools/msys64/`，`bash.exe`、`pacman.exe` 和 `tar.exe`
均已确认存在。通过本地 SOCKS5 代理完成仓库同步并安装了 40 个包；核心工具
版本为 GCC 16.1.0、Python 3.14.6、Ninja 1.13.2、pkgconf 3.0.3、GLib
2.88.2、Pixman 0.46.4 和 libslirp 4.9.3。pacman 最后的 info 索引 hook
曾报告失败，但全部请求的包均能查询且工具可执行，因此不影响 QEMU 构建。

状态：x64 与原生 ARM64 构建环境均**确认可用**。`bbkh1` 已完成启动、NAND、
FTL 空卷初始化和 LCD 非黑屏验证，当前进入 BBK FTL 系统卷重建阶段。

overlay 的 59 个文件已安装到 QEMU 源码树，并通过安装脚本的逐文件内容校验。
可用构建目录为：

```text
work/tools/qemu-11.0.0/build-h1-cross-winpath
```

工作区路径含空格，而 QEMU `configure` 明确拒绝这种源码路径，因此配置时将
源码树临时映射为 `Q:`，将便携 MSYS2 映射为 `R:`。当前机器是 ARM64 Windows，
但安装的是 x64 UCRT64 工具链；Meson native 模式会把 x64 GCC 误配为 ARM64
host。最终采用交叉配置，结果明确为：

| Meson 角色 | 架构 |
| --- | --- |
| build machine | `aarch64` |
| host machine | `x86_64` |
| target machine | `x86_64` |
| QEMU target | `mipsel-softmmu` |
| TCG backend | `x86_64` |

H1 不使用 device tree，配置中禁用 FDT，避免源码包未展开 `dtc` 子模块时联网
下载。配置已于实际 Meson 运行中**成功确认**。x64 Ninja 构建产物为：

```text
work/tools/qemu-11.0.0/build-h1-cross-winpath/qemu-system-mipsel.exe
PE: x86-64
size: 64,071,499 bytes
SHA-256: 8376059ABCA11487FA8AA4DC30454BBCEDE8FDE8B75B1433B0F3BBEA929F36E7
```

该程序的 `--version` 为 QEMU 11.0.0，`-machine help` 同时列出 `bbk9588`
与 `bbkh1`。这是早期 Intel/AMD Windows 发行候选；它仍使用 CRT `longjmp`，
因此不能在当前 ARM64 Windows 的 x64 转译层内执行固件。文末记录的最终构建
已加入无展开跳转兼容层并替代该历史产物。

为获得原生 TCG，另安装了 MSYS2 `clangarm64` 的 Clang 22.1.8、GLib 2.88.2、
Pixman 0.46.4、libslirp 4.9.3、Ninja 1.13.2 等 40 个包，并关闭无关的 tools、
Guest Agent、SDL、GTK、VNC 与 FDT。Meson 确认 `host CPU=aarch64`、
`TCG backend=native (aarch64)`；1563 个 Ninja 目标全部成功。原生构建产物为：

```text
work/tools/qemu-11.0.0/build-h1-arm64-winpath/qemu-system-mipsel.exe
PE machine: 0xAA64 (ARM64)
size: 54,892,032 bytes
SHA-256: 92511B7B972BF3E2D0CDF71AC1D2D2576E1ED110E792B5A95288EB5EB900DE46
```

该程序的 `--version` 为 QEMU 11.0.0，`-machine help` 已确认同时包含
`bbk9588` 与 `bbkh1`。上述哈希对应加入 DMAC 系统地址空间访问与 NAND 地址线
解码后的当前构建；原生 ARM64 构建现作为开发主机上的验证程序，不进入最终
x86-64 发行包。

## H1 首次启动触摸校准

480 x 272 的双色画面是固件的首次启动校准界面，不是桌面加载失败。IDA MCP
已定位完整路径：

```text
校准主函数:  0x8003EE70
校准点绘制:  0x8003FDEC
配置校验:    0x8003FBD8
配置路径:    A:\系统\数据\SysTp.cfg
```

绘制函数从 `0x80473450` 读取四个目标点，顺序为 `(20,20)`、`(460,20)`、
`(460,252)`、`(20,252)`。每个目标点等待一次按下和抬起，记录 SADC 原始坐标，
再计算二维仿射映射。固件会将最后一点反算校验；允许范围是 x=6..34、
y=253..266。

`SysTp.cfg` 固定为 76 字节：

| 偏移 | 字节数 | 含义 |
| ---: | ---: | --- |
| 0 | 16 | 以零填充的产品名 `@ibox H1` |
| 16 | 56 | 7 个 little-endian 64 位仿射/校准值 |
| 72 | 4 | 前述 56 个校准字节的 little-endian 累加和 |

启动时 `0x8003FBD8` 会拒绝长度、产品名或校验和不匹配的文件。QEMU 输入桥接
协议为 ASCII 行 `T x y raw_x raw_y down`；送入 JZ4740 SADC 模型的是原始坐标
和按下状态。状态：**经 IDA 反编译及 QEMU 源码复核确认**。自动完成首次校准并
抓取桌面是当前实现项。

首轮自动校准已依次识别四个十字的 53 个高亮像素，检测中心与上述四个目标坐标
逐点一致；四次按下/抬起后十字消失，画面变为 1,383 色的固件“连接电脑”页。
该页的 480 x 272 PNG 为 `work/emulator/h1-calibration1-desktop.png`，SHA-256
为 `93E875B5E8157D00F39B1FCE4CA0597BC2425DF70D6BFFD54BDFAC84BAFAD2A6`。
这确认了完整资源文件读取、位图解码、UI 绘制和触摸校准输入链路。出现连接页是
因为 machine 的 `usb-power-connected` 默认值为 true，后续桌面验收使用 off。
该页由模拟器实际 framebuffer 抓取确认；外部文章照片不用于推定默认开机画面。
后续未命名画面通过本地 HTML 以原始像素和整数倍缩放交由用户人工确认。

2026-07-29 在一次部署后立即 start/reset 的冷启动中，前三点后固件没有进入第四
点，而是重新显示左上、右上、右下，第二轮后才显示左下。旧网页后端按固定四点
顺序等待，因此在第二轮左上误报超时。保存的帧为
`h1-bda-sdk/build/doudizhu-calibration-timeout.png` 至
`doudizhu-calibration-complete-manual.png`。这次现象证明自动化不能把一次固定
顺序当成完成条件，但不改变上述四个固件坐标和 ADC 样本。后端现改为从每一帧
识别当前出现的任意校准点，按该点发送已验证原始值，允许同一点在 2 秒后重试，
并以触摸开始后连续 1.5 秒没有校准十字作为完成条件；最多 12 次后才判定超时。
RGBA 合成帧对四点检测及无十字帧均有单元回归覆盖。

首轮退出后 NAND 哈希未变化。源码复核确认 `nand-image=` machine 属性通过
`g_file_get_contents()` 载入只读内存；只有 `-drive if=mtd,...` 绑定的 block
backend 才调用 `blk_pwrite()` 和关机 flush。探针已改用可写 MTD backend。
状态：**只读路径及持久化条件经运行哈希和 NAND model 源码共同确认**。

可写 MTD 首轮曾暴露 `bbkh1` 继承 9588 `0xDC` NAND ID 的问题；该次 guest 连续
擦除了 `0x80..0xE4E` 共 3,535 个物理块，只留下 127 个低位逻辑单元。随后仅把
容量字节改为 `0xD3` 仍会复现。IDA 中的 NAND 几何解析函数 `sub_8004B0A0`
进一步证明，扩展 ID 第四字节 `0x95` 表示 128 KiB/64 页擦除块，`0xA5` 才表示
256 KiB/128 页擦除块；而恢复模块和运行时擦除函数 `sub_80048474` 都将块号左移
7，明确按 128 页擦除。旧 ID `EC D3 10 95 44` 因而把两个软件映射记录放进同一个
真实擦除块，回收任一记录会连带擦除相邻记录。这才是 7,196 个映射降为 127 个的
根因；之前的 64 页双槽结论已经撤销。

QEMU 的 `-machine bbkh1,help` 仍显示继承属性元数据的默认值 `220/0xDC`，而同一
实例的 H1 LCD 刷新周期实测为 17 ms。NAND realize 现增加实际 `id-code`、
`pages-per-block`、backing 大小和 page stride 日志。实际启动日志为：

```text
id=ec:d3:10:a5:44
pages-per-block=128
backing-bytes=1107296256
page-stride=2112
```

因此 guest 实际收到的是 1 GiB、128 页擦除块几何，不是帮助文本中的继承默认值。
用户提供的产品参数也明确为 1 GB 内置闪存；2 GiB/`0xD5` 假设已排除。新的全擦除
模板 `work/emulator/h1-1g-a5-template.raw` 已由原固件自行格式化并进入第一个校准
点；初始化后 SHA-256 为
`61D5E7FC87E4C635407977BA4B0E1768F1EEF442BFB5DA84BA27E090F2281203`。
状态：**容量、扩展 ID、128 页擦除几何及旧卷损坏根因均已确认；正在按 256 KiB
单映射单元重建完整系统卷**。

本轮重新构建的开发/交付候选如下；它们都包含 `bbkh1` machine，最终运行目标
仍是 Intel/AMD Windows x86-64：

```text
ARM64 validation build:
  PE machine: 0xAA64
  size: 54,890,496 bytes
  SHA-256: B2456A4FC53813BDDC742488FE5DFEE48FEC690B3554FEC5909CA72A42937F73

x86-64 delivery build:
  PE machine: 0x8664
  size: 64,083,337 bytes
  SHA-256: 27716507724BBDF2961ACEE9A9209FA09EDA8B975E9CAE87B0AB4ACF11D12432
```

这些哈希对应加入 NAND `05/E0` Random Data Output 支持后的当前构建；此前文中
记录的两个构建哈希均为修复前历史产物。重新构建时必须同时把目标工具链 `bin`
和 `work/tools/msys64/usr/bin` 放入 `PATH`，否则 Meson 启动 Ninja 时找不到
`sh.exe`。

## NAND `05/E0` 修复与运行验证

H1 物理页读取函数 `sub_80047310` 先从 column `0x0800` 读取 OOB，再用
`05 + 00 00 + E0` 在同一 row 随机切换到数据区。原 NAND 模型只实现了普通
`00/30` page read，导致 OOB 扫描成功但 FAT 扇区数据读取失败。该缺陷会让
`sub_80055DDC` 返回 `-2`，随后 `sub_80115510` 主动格式化卷；因此此前多种 FAT
构建实验都会得到相同的“四个新映射加一个新 BBT”结果。

修复位于 `emulator/qemu/overlay/hw/block/bbk9588_nand.c`：

- `nand_prepare_page_read_at()` 统一按 page/column 装载读取缓冲；
- 命令 `05` 清空地址锁存，但保留当前读取页；
- 命令 `E0` 使用新的两字节 column 和保留的 row 重新装载数据；
- random read 计入正常 read 诊断事件和计数。

使用原固件自行创建的 A5 模板进行可写控制，logical 0 和 BBT 在 12 秒运行后
分别保持于物理块 `0x44` 和 `0x45`，证明不再触发格式化。详细 FTL 和 IDA 证据
记录在 `docs/08-ftl.md`。

9588 诊断环默认虚拟地址为 `0x89F00000`，storage ring 为 `0x89F02000`；H1
通常只配置 64 MiB RAM，因此这些地址超出 guest RAM。即使用 160 MiB 运行，本次
导出的 `work/analysis/h1-template-storage-trace-2s.bin` 仍为全零。该诊断设施在
H1 路径上未确认可用，不作为 NAND 修复证据；IDA 命令序列、内存导出和可写 FTL
控制是本结论的直接依据。

状态：**ARM64 开发验证构建和 x86-64 交付构建均已重新编译；Random Data Output
修复已通过 guest-native 可写卷验证。x86-64 最终构建的全系统验收记录见文末**。

## 完整 A5 系统卷首次成功启动

修复后的 ARM64 QEMU 已用 `-snapshot` 启动
`work/emulator/h1-1g-a5-system.raw`，machine 参数为
`bbkh1,usb-power-connected=off`。快照模式把写入放入临时 overlay，不复制或修改
1.107 GB 基础 NAND。运行前后基础镜像 SHA-256 均为：

```text
E39D703FECECA817E8D48F769A38391FFB5F7887C5C11811BE0DD5071668E90C
```

首次校准界面不再是空卷的纯色背景，而是从系统卷加载的 H1 主题背景、花形图标和
“请点击目标中心校准屏幕！”文字。第一点 framebuffer 有 400 种颜色：

```text
work/emulator/h1-system-fixed-cal2-calibration/point-1-before.png
SHA-256: CD3E3148621B15FDB22BB1483519125CB8FBC8869A3E9BA9E0E9AAFD49D863D8
```

完整系统主题中的校准十字只有 7 到 8 个精确 `#68B0F0` 像素，而且第一点与左上
花形装饰重叠。探针已改为只检查目标中心 33x33 区域并使用 6 像素阈值；四点分别
在 `(20,20)`、`(460,20)`、`(460,252)`、`(20,252)` 被识别，校准一次完成且
未重启。

校准后出现原固件“系统时间已改变，请重新设置！”对话框：

```text
work/emulator/h1-system-fixed-cal2-after.png
SHA-256: CD9A4B68593681ABF260578FA9E6735AC697C21BF1DCA8052449B15CCA1DF8AB
unique colors: 101
```

选择“否”后进入 H1 主界面并显示“磁盘空间不足，请删除无用文件释放空间！”；该
画面已能看到状态栏、桌面背景及多行系统应用图标：

```text
work/emulator/h1-system-fixed-cal3-after-no.png
SHA-256: 28BF4AD0A5B52F743EEE8E78DE65DEBA4188528181ED98D3F678E2B96D125BA9
unique colors: 5534
```

确认空间提示后，固件显示首次使用的新手引导“滑动移动模块或同时按住〈〉键”：

```text
work/emulator/h1-system-fixed-cal4-desktop.png
SHA-256: 6B8FEEC1786C323D1987B13F179A9D58762B003CD11E1EB93D06B0764A4017C6
unique colors: 5533
```

三次成功运行的 QEMU `guest_errors,unimp` 日志均为 0 字节。上述画面全部来自
QEMU monitor 导出的真实 480x272 framebuffer，未使用网络照片判断 H1 默认界面。
状态：**完整 FAT16/FTL 系统卷挂载、482 文件资源读取、主题/字体/图标解码、触摸
校准和主界面启动均已确认**。当前正在用真实滑动输入退出首次使用引导。

## 应用退出后的桌面背景修复

应用返回桌面后，底部 Dock 正常而上方图标区变成白块的问题已修复。动态现场表明
`0x8057AFC8` 和 `0x8057AFA4` 指向的两个画布对象在应用启动、退出前后都没有释放或
换址；第二画布仍保留绿色壁纸，被清成白色的是第一画布。因此根因不是 Tick、LCDC
双缓冲或画布生命周期，而是桌面恢复路径重新选择了错误的内置资源。

H1 V1.41 固件尝试打开缺失的 `A:\系统\数据\shell\backgro2.bin` 后有两条回退路径：

| 场景 | 函数 | 原指令 | 修正 |
| --- | --- | --- | --- |
| 首次装入桌面 | `sub_8007E7D8`，`0x8007ED78` | `lw v1, 0x1c(v0)` | `lw v1, 0x04(v0)` |
| 应用退出后恢复 | `sub_8008513C`，`0x80085300` | `lw v1, 0x1c(v0)` | `lw v1, 0x04(v0)` |

`desktopc.lib + 0x04` 是有效的绿色壁纸，`+0x1c` 对应零图。machine 只对大小为
`5729640`、SHA-256 为
`D05786E442F9AAD62A8D0A0CB4F6D786BDC7C2FA353A7A2B152C9ED9F01B40EF` 的原始
`project.bin` 应用补丁，并同时校验 `0x7AD68`、`0x812F0` 两段上下文签名；实际改写
偏移为 `0x7AD78` 和 `0x81300`，字节均由 `1C 00 43 8C` 改为
`04 00 43 8C`。此前试验的 `0x83FFF000` trampoline 已删除，因为它只覆盖首次加载，
不能修正独立的应用恢复路径。

ARM64 Windows 构建已完成真实回归：首次进入桌面正常，打开“朗文当代”后按返回，
上方图标区与 Dock 仍共同显示绿色壁纸，无白块。回归截图为：

```text
work/emulator/h1-wallpaper-app-return-fixed.png
SHA-256: A3B56B6C6AF1EA45836DF9C563496EE06F2FD6300625C8897A0D70BA5843B909
```

状态：**首次加载和应用返回两条路径均已动态确认，桌面背景问题完成**。

## 飞天影音首个视频崩溃

选择 `@ibox学习机广告.avi` 后，guest 稳定进入 `0x8002FDC0` 的异常停机死循环；
CP0 `Cause=0x0080841C` 的 ExcCode 为 7，`EPC=0x83C40204`。EPC 所在的
`飞天影音.bda` 指令对 `0xB3080000` 解引用，而当前 machine 没有映射对应的
JZ4740 IPU 物理窗口 `0x13080000`。因此这不是网页输入失效、AVI 文件读取失败或
普通播放器忙等，而是缺失硬件模型导致的确定性数据总线异常。

LCDC 同时仍使用 DA0 的单张 480x272x32bpp framebuffer；该结论不支持用 DA1
合成修改来规避播放器问题。

修复已落实为 `emulator/qemu/overlay/hw/misc/jz4740_ipu.c`，并通过
`bbk9588.c` 把设备映射到物理地址 `0x13080000`、连接 INTC 29。模型实现了：

- `CTRL`、`STATUS`、格式、Y/U/V 地址、输入/输出尺寸与步长、CSC 系数及缩放
  LUT 寄存器的 guest 可见存储；
- `CTRL.IPU_EN` 启动、`STATUS.OUT_END` 完成及 `CTRL.FM_IRQ_EN` 中断语义；
- 平面 YUV 4:2:0/4:2:2/4:4:4/4:1:1 到小端 XRGB8888 的 CSC 转换；
- 最近邻缩放，以及所有输入、输出 DMA 范围相对于 64 MiB guest RAM 的检查；
- 复位位自清除，避免播放器初始化后把 IPU 永久留在 reset 状态。

播放器真实写入 `OUT_GS = width << 18 | height`，因为 RGB888 路径把四字节像素
宽度编码在寄存器高半部；模型据此用 `OUT_GS >> 18` 恢复像素宽度。第一项视频
的前 12 帧限量日志确认了实际契约：

```text
fmt=0x00020004
input=478x272, output=382x217
Y/U/V stride=480/240/240
output stride=1920
Y/U/V buffers alternate between two decoded frames
output=0x029461bc
```

ARM64 Windows 动态回归中，选择 `@ibox学习机广告.avi` 后不再出现数据总线异常；
页面帧序号从 332 持续增长到 855，两张相隔 1.8 秒的真实模拟画面分别显示广告中
不同人物和场景，证明 AVI 解码、IPU 转换和 LCD 刷新均在运行。回归截图为：

```text
work/emulator/h1-video-ipu-playing.png
SHA-256: 8D87B19B51287F1BBC08167AA09ECC8DA853317B84F5DD3B3E524F1708C6510B
```

本轮 ARM64 `qemu-system-mipsel.exe` 大小为 `54,940,160` 字节，SHA-256 为
`C7AE9E2334CFFF10FD09308BBC54BAB7532E7910DE3BFA1DD14EBB3149BC3AB2`。
状态：**飞天影音首个 AVI 的崩溃已修复并完成连续动态画面验证**。

## 应用内右上角触摸坐标偏移

桌面图标和应用中部的大按钮可以点击，但应用右上角的问号、关闭以及文件选择器
右侧“打开”按钮经常无响应。IDA 对固件触摸中断路径的复核表明，应用与桌面共用
同一套输入链路：`sub_80041CC8` 处理 SADC 的 `PEND`、`DTCH`、`PENU`，
`sub_80041FEC` 从 `ADTCH` 连续读取 X/Y 与压力样本并完成五点稳定性过滤，
`sub_80040EBC` 再使用 `SysTp.cfg` 的仿射参数换算为 480x272 屏幕坐标。应用没有
另一套触摸坐标分发函数。

偏移来自网页后端的屏幕坐标反算。原实现错误地把四个校准原始值映射到了屏幕
四角 `(0,0)` 到 `(479,271)`；H1 固件的真实校准目标实际是 `(20,20)`、
`(460,20)`、`(460,252)`、`(20,252)`。因此越靠边缘偏差越大，例如网页点击
`(430,14)`，固件实际约收到 `(415,32)`，会同时向左、向下错过窄小的右上角按钮。

`h1_emulator.py::display_to_raw()` 已改为围绕上述四个真实目标点做双线性逆映射，
屏幕边缘通过同一校准平面外推并限制在 12 位 ADC 范围内。按压/抬起仍保持最短
180 ms 且串行发送；该时序与坐标修复是两个独立问题。

修复后的 ARM64 Windows 实机回归继续使用网页 API 的 480x272 原始坐标，并覆盖了
此前明确失败的坐标：

| 场景 | 点击坐标 | 结果 |
| --- | ---: | --- |
| 时间应用帮助 `?` | `(430,14)` | 进入“帮助--时间” |
| 时间帮助/日期设置关闭 | `(463,14)` | 正确返回上级界面 |
| 时间应用右侧“设置” | `(400,50)` | 进入日期设置页 |
| 朗文当代帮助 `?` | `(430,14)` | 进入“帮助--词典” |
| 飞天影音文件选择器帮助 `?` | `(430,14)` | 进入“帮助--选择文件” |
| 文件选择器“打开” | `(450,260)` | 启动选中的第一个广告 AVI |

同一轮回归中，关闭“朗文当代”后桌面图标区和 Dock 壁纸仍正常；第一个广告 AVI
显示实际视频画面，帧序号继续增长并在片尾正常返回播放器，没有异常停机。

状态：**坐标反算、180 ms 触摸时序和 SADC 输入链路均已动态确认；时间、词典、
文件选择器/播放器三类应用的右上角与右边缘触控回归完成**。

## x86-64 Windows-on-Arm 兼容与最终回归

普通 Win64 QEMU 在当前 ARM64 Windows 的 x64 转译层开始执行 MIPS TCG 后会以
`0xC00000FF` 退出。Windows 将该值定义为 `STATUS_BAD_FUNCTION_TABLE`；固件、
NAND 和 machine 均已加载完成，崩溃发生在 CRT `longjmp` 对 TCG 动态代码栈帧
执行 Windows unwind 时。TCG 生成区没有 Windows unwind 表，因此转译层拒绝
该函数表。

`emulator/qemu/overlay/include/system/os-win32.h` 为 Win64 x86-64 增加了不调用
Windows unwind 的 `setjmp`/`longjmp` 实现。它保存并恢复 Win64 ABI 要求的
RBX、RSP、RBP、RSI、RDI、R12-R15、RIP、MXCSR、x87 控制字和 XMM6-XMM15；
原生 ARM64 和非 x86-64 Windows 路径保持原有实现。加入该覆盖文件后，x86-64
QEMU 在同一台 ARM64 Windows 上不再触发 `STATUS_BAD_FUNCTION_TABLE`。

最终 x86-64 构建通过网页前端执行了完整动态回归：

1. 自动完成四点触摸校准并进入桌面；
2. 打开“朗文当代”的右上角帮助，再依次关闭帮助和应用；返回桌面后图标区与
   Dock 壁纸均正常，无白块；
3. 打开飞天影音和文件选择器，右上角帮助及最右侧“打开”均能响应；
4. 播放 `@ibox学习机广告.avi`，真实画面从启动连续更新到第 1819 帧；
5. 片尾自然返回播放器，QEMU 正常停止并返回进程代码 0。

交付程序为：

```text
emulator/windows-x86_64/bin/qemu-system-mipsel.exe
PE machine: 0x8664 (x86-64)
size: 64,272,665 bytes
SHA-256: DFE53713C4468EE9660F6637CDE89A9A2759D2308054209F7C2369E0B8114440
```

`--version` 为 QEMU 11.0.0，`-machine help` 同时列出 `bbkh1` 与 `bbk9588`。
状态：**最终 x86-64 程序已在 Windows-on-Arm x64 转译层完成桌面、应用恢复、
边缘触摸、文件选择和整段 AVI 播放验收，可直接用于 Intel/AMD x86-64 Windows**。

## H1/9588 继承边界复核

针对后续出现的画面破碎、白色遮挡、无声和随机停顿，已重新复核 `bbkh1` 与
`bbk9588` 的继承关系。两者共享 JZ4740 外设模型和历史文件名，但 H1 并未直接使用
9588 的整机参数：`bbkh1` 单独配置 480x272x32bpp LCD、17 ms 刷新周期、1 GiB
NAND/128 页擦除块、H1 7x6 键盘矩阵和 H1 SSI 路径，并且不实例化 9588 专用
panel/status 设备。因此文件名中的 `bbk9588` 不是白色遮挡的直接原因。

隔离实例已确认飞天影音顶部白条存在于 guest framebuffer `0x01902000`，不是网页
CSS、缩放或颜色转换。播放器的第二套 `player.bin` 资源表也正确声明 index 19 为
`(0,0,480,219)`，原始图像顶部为黑色；应用启动时桌面仍正常，随后才出现约 42 行
白色覆盖。当前结论是继续审计共享 JZ4740 外设语义，尤其 LCD 完成事件、TCU、DMAC、
AIC 和 IPU；这些共享模型若不完整，除了画面还可能影响音频、应用计时、DMA 完成和
系统稳定性。状态：**H1 参数未被 9588 参数直接替代已确认；共享外设行为仍在逐项
动态验证**。

## 模拟精度边界与播放器零页异常

当前 `bbkh1` 已经能够完成 H1 固件启动和主要交互流程，但仍属于功能级系统模拟，
不能宣称为所有 JZ4740 外设的周期精确实现。已知的兼容或近似路径包括：LCD 由固定
17 ms 主机定时器推动完成事件，IPU 使用软件 YUV 转换和最近邻缩放，AIC/DMAC/TCU
的 FIFO、DMA 请求线和中断时序尚未取得实机寄存器轨迹逐项校验；另外，固件缺失
`backgro2.bin` 时使用受固件大小、SHA-256 和上下文签名共同保护的两处兼容补丁。
这些边界必须计入无声、随机停顿和跨应用画面异常的根因分析，不能只以已通过一次
应用流程作为完整硬件验收。

网页输入后端此前把每次矩阵按键强制保持 `320 ms`。这个值不是 H1 实机轨迹或固件
常量，而是早期为避免过短点击漏扫采用的保守值；实际回归已证明它会跨越界面切换：
确认“系统时间已改变”提示的“否”后，同一次仍处于按下状态的确认键会继续落到新界面，
并直接启动桌面上的应用。H1 固件的 `0x80008434` 矩阵扫描路径逐行选择 7 个行引脚，
每行只调用一次参数为 `500` 的短延时；按键中断和扫描并不要求 320 ms 电平。候选值已
缩短为 `80 ms`。后续 Doom 输入遥测证明，H1 machine 只在按下时置位列 GPIO 标志
是错误的：松开没有触发扫描，下一次按下只能先报告上一个键的松开，导致连续命令每隔
一个丢失。machine 现已在按下和松开两次状态变化时都置位对应列标志；方向、确认、
返回的连续序列产生了完整的 10 个按下/松开事件，并依次完成主菜单、Options 和返回
游戏。状态为 **H1 7x6 矩阵按下/松开边沿与连续按键动态确认**。触摸输入仍保留
独立的 `180 ms` 最短时序，因为 SADC 路径包含五点稳定性过滤，不能与矩阵按键混用。

飞天影音白条的内存证据已进一步缩小范围。第二套资源表的 index 19 运行时指针为
`0x8266A598`，目标显存仍为 `0x01902000`。静态 `player.bin` 中该 480x219 图像的
顶部和末行是 `0x00000000` 黑色；运行时相同位置却变成 `0xFFFFFFFF`，随后播放器
通过 `sub_83C035E4` 的逐行复制原样写入显存。资源中有非零像素的行与原文件保持
一致，因此不是网页、LCD 像素格式、缩放、IPU 或整个资源文件选错。

同一异常也出现在第一套播放器皮肤：原始背景中间的大块全零黑色区域在 guest
资源缓冲中变为 `0xFFFFFFFF`，而上下两端的非零控件像素逐字一致。当前最强假设是
NAND/FTL 文件读取链路把全零数据页误判成未编程页或擦除态；它不仅会产生飞天影音
白条，也可能让其他包含大块纯零资源的应用出现白块或破碎。状态：**白条已经从
显示层问题收敛为零数据页语义问题；正在用 NAND 页读取轨迹确认具体责任层**。

构建器复核随后确认了责任点：`scripts/build_h1_system_nand.py` 原先只写入内容非零的
物理页。离线 FTL 读取器会为缺页补零，所以 482 个文件的离线校验能够通过；guest 则
按照真实 NAND 语义把未编程页读成 `0xFF`。修复后的 `write_mapped_unit` 对每一个已有
映射的 128 页单元写入全部数据页及 OOB/ECC，包括内容全零的页。候选完整镜像为：

```text
work/emulator/h1-1g-a5-system-fullpages.raw
size: 1,107,296,256 bytes
SHA-256: 0E44A58159D60EB311C0C2D65158D372214CA8F48356B00A3EC007652743D70E
```

状态：**全零页变成擦除值的构建器根因和修复均已确认；飞天影音及其他应用的动态
画面回归等待包含最新键盘中断修复的 x86-64 QEMU 构建完成后统一执行**。

2026-07-24 的 ARM64 浏览器回归发现默认启动路径仍指向旧镜像：
`emulator/windows-x86_64/firmware/h1-system.raw` 的 SHA-256 为
`E39D703FECECA817E8D48F769A38391FFB5F7887C5C11811BE0DD5071668E90C`，因此进入
飞天影音后顶部白条复现。该现象同时存在于 QEMU framebuffer 和 WebGL 页面，排除
浏览器渲染回归。现已把上述全页镜像部署到默认路径；部署后的大小仍为
`1,107,296,256` 字节，SHA-256 为
`0E44A58159D60EB311C0C2D65158D372214CA8F48356B00A3EC007652743D70E`，没有新增 NAND
副本。ARM64 QEMU 随后从默认路径重新启动，自动校准一次完成；依次关闭时间提示、磁盘
空间提示并进入桌面后，飞天影音初始页的顶部 42 行已经从白色恢复为原资源中的黑色。
QEMU framebuffer 和 WebGL 页面结果一致。状态：**默认启动镜像遗漏部署的原因、修正及
播放器初始页动态回归均已确认**。

## 模拟完整性审计

当前交付目标是让原始 H1 V1.41 固件在 Windows x86-64 主机上达到行为兼容，
而不是宣称已经完成 JZ4740 的周期精确仿真。仅凭两套固件可以确认软件访问的寄存器、
常量和大量状态机分支，但无法确认真实电路的纳秒级时序、模拟噪声、总线争用和未被
固件触发的硬件行为。此前文档中的单次桌面/应用/视频回归只证明对应路径当时可运行，
不能外推为整机所有行为已经完成。

| 子系统 | H1 独立证据与当前实现 | 尚未闭环的精度边界 |
| --- | --- | --- |
| CPU / RAM / 启动 | 原始 MIPS 固件直接运行；64 MiB 范围由 H1 U-Boot 内存测试确认 | QEMU TCG 为指令级功能模拟，不模拟流水线、cache 延迟和总线周期 |
| NAND / FTL | 1 GiB、`0xD3/0xA5`、128 pages/block、OOB/ECC 和 FTL 标签由恢复程序及动态读回交叉确认 | program/erase 延迟、磨损和真实坏块分布仍为功能级模型 |
| LCDC / 面板 | 480x272、DMA 描述符、IRQ 30 和寄存器常量来自 H1 `project.bin` | 完成事件由固定 17 ms 主机定时器推动，尚未按像素时钟模拟欠载和扫描时序 |
| 全键盘 | 7x6 GPIO 连线、扫描公式和两张 42 键码表来自 H1 固件反汇编 | 实物键帽与矩阵位置仍需人工校对；80 ms 宿主脉冲是候选交互参数，不是实机测量值 |
| SADC 触摸 | 五点校准、原始坐标反算、`PEND/DTCH/PENU` 及应用边缘点击已动态验证 | 压力、抖动、ADC 噪声与板级 RC 特性为合成值，未取得实机采样轨迹 |
| IPU | H1 飞天影音的 MMIO 地址、格式、地址和完成中断路径已确认 | 当前帧在宿主立即软件转换，缩放为最近邻；不模拟硬件处理延迟和全部滤波模式 |
| AIC / codec | H1 初始化代码确认地址、格式、DMA request 24/25；模型具备 FIFO、DMA 和宿主音频输出 | codec 模拟寄存器和 FIFO/中断时序尚未与实机轨迹逐项比对，是无声和卡顿的高风险项 |
| DMAC / TCU / INTC | 固件使用的通道、请求号、计数器和中断入口已逆向，已有功能状态机 | DMA 仲裁、请求线边沿和定时器相位未做实机级比对，是随机停顿的高风险项 |
| SSI | H1 使用的 `0xB0043000` 和 IRQ 16 已确认 | 当前仅为 idle/always-ready 控制器；连接的板载 SPI 器件身份和协议尚未确认 |
| USB UDC / CIM | 固件寄存器访问路径有模型承接 | UDC 没有 USB 包传输和端点 FIFO；CIM 只有空闲控制器，不能算完整硬件实现 |
| CPM / RTC / 电源 | 12 MHz 晶振、PLL/分频及 RTC/休眠寄存器路径已实现 | 时钟门控对每个外设的传播、电源管理和实物唤醒线路尚未完整验证 |
| 固件兼容路径 | `backgro2.bin` 缺失时的两处补丁受版本大小、SHA-256 和指令签名约束 | 这是明确的兼容性捷径，不是硬件模拟；应在找到原始资源或真实回退语义后移除 |

因此，`bbkh1` 不是直接把 9588 的整机参数换个名字：H1 的 RAM、LCD、NAND、键盘和
SSI 均有独立配置；但它确实继承了 9588 项目起步时的共享 JZ4740 外设框架。共享模型
未经过 H1 实机轨迹验证的部分，除了画面，还可能影响音频、按键、触摸、应用计时、
DMA 完成、USB 和长期稳定性。此前无依据的 320 ms 按键保持以及固件壁纸补丁都属于
为先跑通流程采取的捷径，必须明确记录，不能作为已经研究清楚实机行为的证据。

后续验收按行为面而不是单张截图执行：方向/确认/返回不得跨界面穿透；桌面与多个应用
往返后显存保持一致；触摸覆盖帮助、关闭、列表和屏幕边缘；AVI 画面与音频连续；多应用
循环和空闲运行至少 30 分钟无停机。只有对应测试通过并能关联到 H1 固件或实机证据时，
该行为才标记为确认。

## H1 充电检测与独立电源键

H1 的电源相关 GPIO 已根据 `project.bin` 的实际访问路径与休眠中断状态重新核对，不能继续沿用 9588 的板级连线。

已确认的固件证据：

- `sub_8002DE44` 读取 `0xB0010300 & 0x40`，即 GPIO `PD6`，非零表示充电器已连接；调用链在该状态下把电池电压视为 4200 mV。
- `sub_8002F520` 持续读取 `0xB0010300 & 0x20000000`，即 GPIO `PD29`，用于独立电源键事件。
- 完整休眠时 CPU 停在 `0x800317FC` 的 `WAIT`，GPIO2 中断被屏蔽而 GPIO3 保持为唤醒源。矩阵确认键位于 GPIO2，不能用于唤醒；`PD29` 位于 GPIO3，与固件和中断掩码同时吻合。
- `PB18` 是 H1 7x6 键盘矩阵的行线之一。9588 的 active-low `PB18` USB/充电检测属性不得驱动 H1。

模拟器实现已经按型号分离：

- `bbkh1` 的 `charger-connected` 属性驱动 active-high `PD6`，默认连接充电器，避免无人测试时把正常休眠误判为随机卡死。
- `bbk9588` 的 `usb-power-connected` 仍只驱动 active-low `PB18`；H1 路径不再受它影响。
- H1 主机输入代码 `44` 是独立电源键，按下/松开只改变 active-low `PD29`，依靠 GPIO3/INTC 的真实中断路径唤醒 CPU，没有从主机端直接跳过 `WAIT`。
- 网页工具栏提供电源图标；常驻的方向、确认、返回六键和抽屉式全键盘布局保持不变。
- 网页默认勾选“连接充电器”，可运行时切换；后端通过 QOM 属性即时改变 `PD6`，也可用 `--no-charger` 从断开状态启动。

Windows x86-64 动态验证中，运行时断开充电器后 GPIO D 输入从 `0x6020007c` 变为 `0x6020003c`，`PD6` 被清零；重新连接后恢复为 `0x6020007c`。两次 QOM 操作均返回成功，QEMU 持续运行且后端无错误。状态：**H1 的 PD6 充电检测和运行时切换已动态确认**。

断开充电器后，固件进入 `0x800317FC` 的真实 `WAIT`。网页电源键按下时 `PD29` 从高电平变低，GPIO D 输入为 `0x4020003c`；CPU 随即离开 `WAIT` 并运行到 `0x8002F6DC` 的电源事件处理路径，按下和松开事件均被后端接受。状态：**PD29 -> GPIO3 -> INTC -> CPU 的休眠唤醒链已动态确认**。

本次唤醒后，固件又主动写入 RTC `HCR.PD` 并使 QEMU 以代码 0 正常退出。它不是 QEMU 崩溃，但尚需区分当前空闲计数/电源状态是否本就要求关机，以及正常待机唤醒流程是否还缺少其他板级信号。后端同时修正了正常关机时 frame socket 被关闭所产生的假错误：退出代码为 0 时不再把 `ConnectionResetError`/`EOFError` 报成模拟器故障。

待动态验收：普通待机唤醒后持续运行、充电状态下长时间运行，以及断开充电器后的真实自动休眠/关机流程。

## 飞天影音音频连续性

最初的网页观测只能证明每个约 20 ms 的音频包持续到达，不能证明包内每一帧都来自
DMA。为区分网页调度和 guest FIFO 欠载，AIC/DMAC 模型及后端状态接口增加了累计输出
帧、FIFO 空读、DMA 样本、完成/重装次数、完成到重装间隔和间隔内欠载计数。新的证据
推翻了“只有网页调度问题”的结论：网页收到的 PCM 在进入 WebSocket 前已经包含 AIC
FIFO 空读产生的保持值或静音。

普通 QEMU 虚拟时钟、`tcg,thread=multi` 和 Windows 普通进程优先级下，x86-64 QEMU
在 Windows-on-Arm 上播放广告时的 20.030 秒窗口得到：

```text
网页音频帧        884,306 (44.15 kHz)
AIC 实际处理帧    846,627 (42.27 kHz)
FIFO 空读         154,410
DMA 完成          499
```

这比当时把 `thread=single` 与 instruction-count 时钟同时启用时约 35.5 kHz 的有效输出
明显改善，但仍有可闻断续。后续 A/B 证明慢速来自 `-icount shift=auto,sleep=on`，不能
归因于单独的 `thread=single`。instruction-count 模式还要求单线程 TCG，并会使自动校准
在第三阶段超时，因此不作为默认配置。随后同步当前 H1 外设覆盖并重新构建原生 Windows
ARM64 QEMU；该中间版本大小 54,961,664 字节，SHA-256 为
`2DA5B3BBEA54B38E162402191B67612D33C6652E3E9B275733444FBDDDEF1354`。
同一 NAND、固件和广告的 8.023 秒 ARM64 窗口得到：

```text
网页音频帧        356,169 (44.39 kHz)
AIC 时钟处理帧    358,362 (44.67 kHz)
FIFO 空读         279,180
DMA 完成          142
视频帧            100 (12.46 fps)
```

因此 TCU/AIC 虚拟时钟不是整体偏慢：它们继续按约 44.1 kHz 的墙钟速率消耗 FIFO。
H1 TX FIFO 只有 32 个 16 位样本，即 16 个立体声帧，在 44.1 kHz 下仅覆盖约 0.36 ms；
宿主线程一次较长的调度停顿就会被错误放大为 guest 可见欠载。修复前的 ARM64 四秒窗口
中，DMA 完成/重装约为 `114/114`，累计重装间隙为 49--58 ms，FIFO 空读为
4,648--4,880 次，单次最大间隙约 10.99 ms。

AIC 现于 DMA terminal count 后暂停处理待输出帧，直到固件重装缓冲区并产生第一次 DMA
写入。FIFO 深度、阈值、寄存器、DMA 请求和完成中断语义不变；宿主线程被调度出去的时间
不再合成为硬件欠载。为避免媒体结束后长期空闲积累旧帧，边界等待超过 100 ms 时下一次
DMA 写入会清除旧积压，等待期间积压上限为 250 ms；播放关闭、软复位、设备复位和迁移
恢复也会清除边界时间戳。

H1 只有一个 MIPS vCPU。普通虚拟时钟下对同一广告做 ARM64 A/B，证明 MTTCG 的锁和
调度开销会在复杂解码段产生长尖峰，而单线程 TCG 更稳定：

| TCG 模式 | 窗口 | guest 吞吐 | 视频帧 | AIC 输出帧 / 有效频率 | 累计重装间隙 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `thread=multi` | 31.321 s | 4.57 MIPS | 825 | 1,276,359 / 40,751 Hz | 3,749.514 ms |
| `thread=single` | 32.312 s | 4.94 MIPS | 934 | 1,424,954 / 44,100 Hz | 541.206 ms |

单线程窗口内 DMA 完成/重装增加 `968/968`，AIC 欠载和重装间隔欠载均为 0，视频帧龄
持续低于 80 ms。整段播放结束时为 `1726/1725`，最后一个 DMA 缓冲区完成后固件不再
重装，这是正常的媒体结束状态；本轮最大有效重装间隙为 42.316 ms。结束并空闲 51 秒
后重播，前 0.5 秒只产生 14,510 帧，没有旧 PCM 突发；随后 10.104 秒产生 445,796 帧，
即 44,120 Hz，DMA 再次追平且零欠载。后端默认因此改为
`tcg,thread=single,tb-size=256`，同时保留 `--tcg-thread multi` 作为诊断开关。

原网页在已排队音频不足 20 ms 时会调用 `resetAudioQueue()`，这会停止尚未播放完的
`AudioBufferSourceNode`，再从墙钟后 40 ms 重新开始。只要 WebSocket 或主线程出现轻微
抖动，就会主动截断当前声音并制造空隙。现改为首包预缓冲 120 ms；正常低水位不再
停止已排队节点，只有确实落后于音频墙钟时才从 10 ms 后续播；积压超过 1 秒时才丢弃
陈旧队列并重新同步。该修改消除了网页主动截断，但不能修复上游已经缺失的 DMA 样本。
网页端在自动化浏览器的 AudioContext 被手势策略挂起时，2.5 秒仍收到 129 个 PCM
WebSocket 消息，证明页面数据通道连续；实际出声必须由用户在页面上的真实点击解锁。
当前 ARM64 二进制为：

```text
work/tools/qemu-11.0.0/build-h1-arm64-winpath/qemu-system-mipsel.exe
PE machine: ARM64
size: 54,961,664 bytes
SHA-256: 5FFAC844065A048C2514CE12E6D7DCE0B3666F77619B2C939DAE51F41F075F1C
```

状态：**ARM64 的 AIC/DMAC、普通虚拟时钟、32 秒活动播放和 51 秒空闲重播连续性已通过；
网页真实听感等待人工确认。本轮按要求没有重编译或更新 x86-64 QEMU。**

## ARM64 原生 SDL 输出隔离测试

用户确认 8793 页面位于前台时画面和声音同时卡顿，页面不在前台时声音恢复，因此增加
完全绕过浏览器绘制、WebSocket 和 WebAudio 的隔离路径。ARM64 MSYS2 工具链新增
SDL2 2.32.10，QEMU 11.0.0 重新配置为 `sdl=enabled`；`-display help` 已确认新增
`sdl`，`-audiodev help` 已确认包含 `sdl` 和 `dsound`。

`bbk9588-host-input` 同时注册 QEMU 原生输入处理器：SDL 左键按下/松开按四点标定参数
反算为 H1 SADC 原始坐标；方向、Enter、Esc/Backspace 分别映射到已确认的 H1 键号。
该路径不要求 `input-chardev`。DirectSound 在当前 Windows 虚拟机中因没有可用的录音
采集设备而拒绝初始化，改用 SDL 音频后端后原生窗口成功启动并持续运行。

本次隔离实例不启动 Python/8793，不配置 `frame-chardev`，使用
`-display sdl -audiodev sdl,id=h1audio,in.voices=0`。当前 ARM64 二进制为：

```text
work/tools/qemu-11.0.0/build-h1-arm64-winpath/qemu-system-mipsel.exe
PE machine: ARM64
size: 55,108,096 bytes
SHA-256: 2B82CCCC4F3786FCB261B107DD29D6C233CDC8F31A254D25FAD41BD1C9445789
```

人工验收使用同一 ARM64 QEMU、同一固件和 NAND，在 SDL 原生窗口中播放学习机广告，
画面与声音均连续正常。与 8793 页面前台时音画同时卡顿、页面退到后台后声音恢复的
对照结果共同确认：当前卡顿来自浏览器前台的帧绘制、WebSocket 分发或 WebAudio
调度链路，不是 MIPS 来宾执行、IPU、AIC/DMAC 或 QEMU 整体定时器偏慢。

状态：**SDL 原生显示、原生输入、SDL 音频及广告音画流畅度均已人工确认；浏览器输出
链路是剩余卡顿的责任域。本轮仍未构建或更新 x86-64 QEMU。**

## 浏览器音画链路拆分与工作线程缓冲

原网页把控制/状态、约 522 KiB 的 RGBA framebuffer 和 PCM 包串行写入同一条
WebSocket。画面发送或主线程 `putImageData()` 稍慢时，音频必然排在大帧之后；音频端还
每约 20 ms 在主线程逐样本转换并新建一个 `AudioBufferSourceNode`。这解释了页面位于
前台时音画一起卡，而相同 QEMU 使用原生 SDL 时流畅的对照结果。

后端现将三类数据分别放在 `?stream=control`、`?stream=frame` 和 `?stream=audio`
三条 WebSocket 上。画面发送线程只取最新 framebuffer，慢消费者不会阻塞 PCM；浏览器
使用 WebGL 纹理上传绘制 RGBA 帧，只在 `requestAnimationFrame` 中消费最新一帧。
PCM 由独立 `AudioWorklet` 写入环形缓冲，在音频渲染线程完成 S16LE 转换及 44.1 kHz
到宿主 48 kHz 的线性重采样，不再依赖主线程定时创建音频节点。无 AudioWorklet 时仍
保留原 `AudioBufferSourceNode` 兼容路径。

初版环形缓冲在无头 Edge 中连续 12 秒没有欠载或溢出，但队列累积到约 703 ms。为避免
长期音画延迟，工作线程加入以 180 ms 为目标的缓慢漂移校正：队列高时消费速率最多提高
5%，队列低时最多降低 1%，不修改 guest AIC/TCU 时钟，也不周期性清空整包。最终同一
广告的 12 秒 ARM64 + Edge 回归结果为：

```text
画面消息                 352
画面最大到达间隔         105.1 ms
PCM 包                   563 / 534,346 frames
PCM 最大到达间隔         39.3 ms
AudioWorklet 欠载        0
AudioWorklet 溢出丢帧    0
最终队列                 5,875 frames / 133.2 ms
最终漂移校正             -0.187%
AudioContext 输出率      48,000 Hz
```

重复测试脚本为 `scripts/test_h1_browser_runtime.mjs`；它通过本机 Edge DevTools 直接
断言 WebGL、AudioWorklet、PCM、欠载和溢出状态。状态：**浏览器传输队头阻塞、主线程
音频调度和长期缓冲漂移均已修正并完成自动回归；真实前台听感等待人工验收**。

## 浏览器单页双轨回声

人工验收确认仅有一个 `?stream=audio` WebSocket 时仍能听到前后相邻的两轨声音。
源码复核确认 `jz4740_aic_process_output()` 会把同一批 PCM 同时送入两个出口：
`jz4740_aic_stream_output()` 通过 host bridge 发往浏览器，随后 `audio_be_write()` 又
写入 QEMU 的宿主音频后端。浏览器路径有额外的网络和 AudioWorklet 缓冲，因此两轨
存在很短的时间差，听感表现为回声，而不是多网页重复播放。

第一轮隔离使用 `-audiodev none,id=h1audio`，人工复测确认双轨消失，但声音和画面重新
出现卡顿。运行时 AIC 仍输出 44.1 kHz 且 FIFO 欠载为 0，DMA 重装间隔却出现最高约
312 ms 的调度尖峰，因此 `none` 后端不能作为浏览器模式的最终方案。

JZ4740 AIC 现增加 `host-output-muted` 属性。8793 恢复原来流畅版本使用的默认宿主音频
后端及 `audio_be_write()` 节奏，只在 `audio_be_set_volume_out_lr()` 对宿主 voice 设置
静音；`jz4740_aic_stream_output()` 在这一步之前独立生成浏览器 PCM，不受该属性影响。
网页启动参数使用 `-global jz4740-aic.host-output-muted=on`，原生 SDL 启动方式默认仍有声。
页面独占、可见性暂停和多页面断连逻辑没有恢复。ARM64 增量构建后的二进制大小为
55,108,096 字节，SHA-256 为
`A07B6D70FCFE823A862F991570F0414A0C7385F0B50F8C556E452E4D6B22E6B4`；设备属性帮助和
8793 实际进程命令行均已确认启用 `host-output-muted=on` 且不含 `-audiodev none`。
状态：**`none` 后端方案已否决，宿主 voice 静音方案已完成 ARM64 构建和启动验证，等待
单页人工复测无回声及音画流畅度**。

## 飞天音乐 seek / 停止后重播 DMA 死锁

人工复现的卡住状态不是网页音频队列问题。`/api/status` 连续 41 秒内画面序号、音频包、
`tx_dma_samples`、`output_frames` 和 DMA 完成数均不再增加，但 MIPS 指令计数仍持续推进。
此时 H1 使用 DMAC channel 3，固件已经重新装载下一段音频：

```text
AICFR=0x00001f31  AICCR=0x00094002  TX FIFO=31
DSA=0x00a2c000   DTA=0x10020034   DTC=0x00000900
DRT=24           DCS=0x80000001   DCM=0x0080a202
```

`AICFR.TFTH=15` 对应 TX DMA 阈值 30 个样本。旧的宿主调度补偿逻辑在 DMA terminal
count 后无条件暂停 FIFO 消耗，并只在下一次 DMA 数据写入时解除暂停。上述状态中 FIFO
为 31，DMA 请求线尚未达到阈值；DMA 虽已重新使能，却等不到请求，AIC 又因边界暂停永远
不会从 31 消耗到 30，于是形成确定性的循环等待。这解释了正常顺序播放大多可用，而 seek
或停止后直接点歌名因边界时 FIFO 相位不同而稳定卡住。

修复原则是保留 terminal count 对宿主长调度间隙的补偿，但边界时若 FIFO 高于固件配置的
阈值，仍允许排空到阈值，使已经重装的 DMA 获得真实请求；没有重装时则停在阈值等待，
不继续合成欠载。`AICCR.FLUSH` 同时清除边界和旧的待输出帧，避免停止/seek 后把上一条流
的等待状态带入下一条流。

ARM64 增量构建后执行两条真实 UI 回归：从 00:04 点击进度条跳到约 02:31，连续 7 秒
UI 时间、画面、PCM、DMA 样本及完成/重装数均持续增长；点击停止时完成数正常比重装数
多 1，直接点击播放列表中的 `步步高.mp3` 后 1 秒内重新装载，随后 7 秒内再次保持完成/
重装相等和零 FIFO 欠载。新二进制为：

```text
work/tools/qemu-11.0.0/build-h1-arm64-winpath/qemu-system-mipsel.exe
PE machine: ARM64
size: 55,109,120 bytes
SHA-256: 8AFC82633ED895167B8681E376D95722DF1FB845E661196BF5B7325F69021525
```

状态：**飞天音乐 seek 及停止后点歌名重播的 DMA 死锁已修复并完成 ARM64 动态回归；
本轮未构建 x86-64**。

## 游戏低采样率音频回归

“中国象棋”不能从“幸运BBK”进入：后者本身会卡住。有效测试路径是桌面分类切换到
“其它”，向左翻到第二页后直接启动“中国象棋”，再确认游戏收费提示。收费提示阶段
AIC 保持复位空闲是预期行为；进入游戏后固件配置为：

```text
sample rate=11025 Hz  AICFR=0x00001f31  AICCR=0x00094802
TX FIFO=31           DMA completions/rearms=640/640
TX DMA samples=640795 AIC output frames=640764  underruns=0
```

该路径与飞天音乐的 44.1 kHz 配置不同，证明修复作用于 AIC FIFO/DMAC 请求阈值语义，
不是对播放器或某个采样率的特判。进入游戏后连续观测超过 12 秒，画面、PCM、DMA 和
AIC 输出持续推进；用户同时人工确认中国象棋默认背景音乐听感正常。状态：**中国象棋
11.025 kHz 游戏音频已完成动态及人工验收；“幸运BBK”卡死作为独立问题保留，不混入
本次音频结论**。

## H1 CC2500 联机硬件

“飞鸽传书”和“幸运BBK”启动时都会进入 H1 公共的 CC2500 初始化路径。启动后
SSI 从复位值变为 `CR0=0x8006`、`CR1=0x14000060`，而 CPU 长时间停留在
`0x802716D0..0x802716FC`。IDA 已确认该循环不是延时函数，而是在 `PD19`
片选拉低后等待 `PD21` 上的 CC2500 SO 就绪低电平。

原 `jz4740_ssi.c` 只回读刚写入的 SSI 数据并始终报告传输完成，既没有 CC2500
协议状态，也没有把 SO 连到 GPIO。因此它不足以代表 H1 的联机硬件。实现目标已经
确定为：

- 由 SSI 设备解释 CC2500 单寄存器/突发读写、命令选通和 FIFO 访问；
- 返回 CC2500 的 `PARTNUM`、`VERSION`、`MARCSTATE`、`PKTSTATUS`、
  `TXBYTES` 和 `RXBYTES` 等状态；
- 由板级 `PD19` 控制每次 SPI 事务边界，并把设备 SO 就绪状态反馈到 `PD21`；
- 固定不注入接收包、载波或接收 GDO 事件，使扫描结果稳定为空；发送真实报文时仍按
  `IOCFG0=0x06` 产生 `PD24/GDO0` 报文结束下降沿，使发送状态机正常推进。

SSI 模型现已实现 CC2500 配置/状态寄存器、PATABLE、TX FIFO、单次及突发传输和
全部 `0x30..0x3D` 命令选通；`RXBYTES=0`、`PKTSTATUS=0` 且不产生接收事件。
板级 GPIO 写回调用 `PD19` 划分 SPI 事务，GPIO 采样回调则只在片选有效时把
`PD21/SO` 拉低。

首轮动态测试越过 SO 轮询后进入 `PANIC:illigeal interrupt expired:142`。中断号
`142 = 48 + 2 * 32 + 30` 对应 NAND `R/B#` 的 `PC30`。现场 Port C
`IM=0xFFFFFEFF`，其中 `PC30` 明确为屏蔽状态；原 GPIO 模型却只按 `flag != 0`
驱动端口 IRQ，完全忽略 `IM`，且改变 `IMS/IMC` 后不重算 IRQ。修复后 IRQ 电平只由
`flag & ~IM` 决定，并在屏蔽寄存器变化后立即更新。由 NAND 完成事件置位但已经屏蔽的
`PC30` 不再错误调用默认 handler。

第二轮测试中飞鸽传书能进入个人设置，但 CPU 等待 `0x80A6C1F8`。固件证据表明：

- `PD24` 被配置成 GPIO 边沿中断，handler 为 `0x802714F4`；
- CC2500 `IOCFG0` 被写为 `0x06`，即同步字发送/接收时 GDO0 拉高，报文结束时拉低；
- 应用在 `STX` 后等待该下降沿把完成标志置 1。

因此 SSI 模型在 TX FIFO 非空、`IOCFG0=0x06` 的 `STX` 上报一次板级发送完成，板级
再锁存 `PD24` 下降沿；无报文或其它 GDO 配置不触发。接收侧仍保持无包、无载波和
无同伴。动态回归已完成：飞鸽传书保存昵称后进入空收件箱，广播发送完成且没有发现
任何机器；退出后从“其它”分类启动“幸运BBK”，正常进入“协同学习-幸运BBK”主界面，
连续观察 6 秒进程和 MIPS 指令计数持续推进，无 panic 或重启。

ARM64 增量构建已通过，新二进制为：

```text
work/tools/qemu-11.0.0/build-h1-arm64-winpath/qemu-system-mipsel.exe
PE machine: ARM64
size: 55,116,800 bytes
SHA-256: 46A58E2529C77CDDFCC1007BEB9E177A104EC5C4DE7190A84A45606C470B77AD
```

状态：**CC2500 身份、SPI 协议、SO 就绪、PD24/GDO0 发送完成、空 RF 环境及 GPIO
中断屏蔽语义均已实现并完成 ARM64 动态回归；飞鸽传书和幸运BBK 已正常运行。本轮
未构建 x86-64**。

## 网页全键盘抽屉可见性修复

全键盘按钮原本已经正确切换 `aria-expanded` 和抽屉的 `hidden` 属性，但抽屉位于
`.stage` 普通文档流的最末端。桌面浏览器中，960 像素宽的 480×272 画面、常驻六键、
顶栏和间距之和已经超过 720 像素高的可视区域；点击按钮后键盘实际展开在窗口下方，
用户看到的只有按钮颜色变化，表现为“点击不能打开”。该问题与输入协议或 QEMU
按键矩阵无关。

抽屉现改为 `position: fixed` 的窗口底部面板，并增加始终位于面板右上角的关闭按钮；
键盘主体仍限制为 960 像素，窄窗口通过面板内部横向滚动访问全部 H1 按键。ARM64
8793 页面动态验证结果：

```text
viewport: 1280 x 720
drawer:   left=0 top=492 right=1265 bottom=720, position=fixed
open:     aria-expanded=true, hidden=false
A key:    input event counter 150 -> 152 (press + release)
close:    aria-expanded=false, hidden=true
```

状态：**全键盘打开、可见、关闭和真实按下/释放输入均已动态确认；静态网页直接生效，
未重启或复制 QEMU 进程**。
