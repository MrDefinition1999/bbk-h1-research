# 项目重建状态

更新日期：2026-08-04

本页只记录磁盘事故后的可复现重建结果。历史运行结论仍需结合
`H1项目重建交接说明.txt` 阅读；旧文件存在不等于内容可信。

## KOV 构建链：已重建并确认

以下损坏文件已移入 `work/rebuild/corrupt-originals/`，重建文件不再包含原覆盖
数据：

- `h1-bda-sdk/ports/kov_pgm/build_port.py`
- `h1-bda-sdk/ports/kov_pgm/tests/test_sound.py`
- `h1-bda-sdk/ports/kov_pgm/tests/decrypt_runner.c`
- `references/fba-a320/src/cpu/cz80/cz80_op.c`

前两个 Python 文件由同版本 Python 3.14 字节码恢复，并与参数、常量、控制流逐项
核对。`decrypt_runner.c` 依据公开的 V119 解密 API、固定合成向量和私有参考文件
接口重建。另确认两个头文件的目录项已丢失并完成重建：

- `h1-bda-sdk/ports/kov_pgm/include/kov_decrypt.h`
- `h1-bda-sdk/ports/kov_pgm/include/kov_pack.h`

`cz80_op.c` 仅该文件与审核哈希不一致；现已从固定提交
`fba-a320@68af7cc` 的干净浅克隆逐字节恢复，SHA-256 为
`3E5FF66BDB62A81AE2D4ABA56676014EF5838923157A601A737AE03A3B041BB5`。

Windows ARM64 的 x64 转译层会在 A68K 生成器退出后短暂保留可执行文件句柄。
`generate_a68k.py` 现以最多 20 次、每次 50 ms 的有界重试清理生成器；KOV 临时
目录允许忽略退出时仍被系统短暂占用的文件，不影响生成内容。

验证结果：

- KOV 主机及 MIPS32R1 测试：10/10 通过，无跳过。
- `-Wall -Wextra -Werror` 的 host C 和 MIPS 交叉编译均通过。
- A68K 和 CZ80 生成、完整 MIPS 编译、链接、图标打包和 H1 BDA 校验通过。
- 在 `SOURCE_DATE_EPOCH=0` 下连续两次构建字节完全一致。
- ROM-free 开发验证包大小：703,812 bytes。
- ROM-free 开发验证包 SHA-256：
  `07BEAA46ADB52E13DC4A368985A5F1B7DBE154B267B264B04E3F28EDE4783F2D`。
- 构建输出明确标记 `roms_embedded=no`；该验证包不是实机发布包。

## 隔离工具链：已确认

- w64devkit 2.9.0 x64 下载 SHA-256：
  `BFF1D13FC2718EEBD93548CF37F8D0332D925458D5E99506CFF8F46EB5A9DE5A`。
- MSYS2 base x86-64 20260611 下载 SHA-256：
  `A2D047E8EE213C3C6A49A8DE427EB1069DF12207C0422FF1B3CBB5C905C34221`。
- MSYS2 UCRT64 clang 22.1.8 成功生成 little-endian MIPS32 对象；这是当前
  SDK/KOV 的已验证交叉编译器。
- llvm-mingw 20260616 和官方 LLVM 19.1.7 Windows 包均不能提供本项目所需的
  MIPS `-G0` 后端选项，已判定不可用，不得接入 H1 构建。
- Python/Pillow 安装在 `work/rebuild/venv/`，该环境含本机路径，只用于开发，
  不得进入发布物。

## H1 专用 IPU：已重建并完成编译隔离验证

原 `emulator/qemu/overlay/hw/misc/jz4740_ipu.c` 是 13,776 字节的非源码覆盖，
已移到 `work/rebuild/corrupt-originals/emulator/qemu/overlay/hw/misc/`。现有
源码模型依据 Dingoo SDK 的 `Jz4740_23_ipu_spec.pdf` 和 H1 播放器实测轨迹重建，
没有复制 9588 的实现。

模型覆盖控制/状态/格式/地址/几何/stride/CSC/缩放寄存器、`IPU_EN` 启动、
`OUT_END` 完成和 IRQ 29；支持常用 YUV 4:2:0/4:2:2/4:4:4、RGB555/565/888
输出、最近邻缩放、guest RAM DMA 范围检查及非法 DMA 的可收敛完成状态。
它是功能级模型，不宣称模拟完整硬件滤波延迟。

QEMU x86-64 cross Meson 配置已经成功，IPU 对象已实际进入
`libqemu-mipsel-softmmu.a` 的编译图；ARM64 原生配置仍受 MinGW ARM64
`setjmp/longjmp` 检测限制，和 IPU 源码无关。

## CS15 参考文档：已重建

`docs/12-cs15-lite.md` 原文件被无关 PowerShell 文本覆盖，已隔离为
`work/rebuild/corrupt-originals/docs/12-cs15-lite.md.injected`，并依据公开
`references/CS15-Lite-for9588/` 与 H1 SDK 事实重写。该页明确 9588 ABI 不能直接
用于 H1，也明确当前没有可信 H1 CS15 BDA 或资源包，避免误把历史失败包当作发布物。

## x86-64 QEMU 构建：已完成

目标为 `mipsel-softmmu`，host 为 x86-64，TCG 使用本机 x86-64。最终 PE
machine 为 `0x8664`，`--version` 报告 QEMU 11.0.0，`-machine help` 同时列出
`bbkh1` 和参考用 `bbk9588`。去符号和本机路径净化后的文件为：

- `emulator/windows-x86_64/bin/qemu-system-mipsel.exe`
- 大小：10,544,640 bytes
- SHA-256：`71D262B5ABEA05E96F98C7B379677C820A540EF54922EAB9AF4354409D3E3302`

QEMU 所需动态库已作为运行时依赖放入同一 `bin` 目录，不依赖开发机 `R:`
工具链。Windows 前端的 Python 3.14 运行时也已补齐；解释器、前端标准库导入和
`h1_emulator.py --help` 均通过。

## 公开源码覆盖恢复：已完成当前 NUL 筛查

doomgeneric `dcb7a8d`、Carnage3D `1cddd91` 和 OpenGTA `1ae34ae` 的干净浅克隆
均与事故前本地 HEAD 完全一致；58 个含 NUL 的第三方文件已从这些提交恢复。
Chocolate Doom 的 `opl.h` 与 `wf_rom.h` 分别从文档固定的 `d61a801` 与
`353cf50` 恢复，许可证也从对应提交恢复。

项目自有 `examples/system/memory/memory_demo.c` 依据已动态验证的 H1 heap API
重建。测试 BDA 大小 31,316 bytes，SHA-256 为
`DFC6E0FCEC095F76E3062C40F9F24D586BFEB38142C1BC562A706EACD6DC3449`，H1 BDA
结构校验通过。除生成目录外，当前 `docs/scripts/h1-bda-sdk/emulator` 文本扩展名
筛查未发现剩余 NUL 覆盖。

KOV 主机及 MIPS 回归重新执行为 10/10 通过；测试候选工具链路径已加入事故后
固定的 `work/rebuild/tools/` 位置。

## 2026-08-04 全树与回归复查

对 `docs/`、`scripts/`、`h1-bda-sdk/` 和 `emulator/` 中 848 个项目自有文本
文件重新逐字节检查，结果为 NUL 文件 0、空文件 0。敏感命令特征扫描只有交接
文档中对旧 Defender 误报的说明文字命中，不存在可执行的 HMP `TcpClient`
脚本残留。

旧 `work/tools/DingooPie-src/w64devkit/bin/gcc.exe` 虽仍能读取文件属性和哈希，
Windows 创建进程时返回错误 1392（文件或目录损坏且无法读取）。KOV 测试与辅助
工具现优先使用事故后重新展开并实际执行验证的 MSYS2 20260611 GCC/Clang，且补正
w64devkit 2.9.0 的实际嵌套目录。修复只涉及宿主工具发现，不修改 MIPS 游戏逻辑、
优化参数或发布产物。

重新执行结果：

- H1 SDK 与 A320 兼容层：76/76 通过；
- KOV 主机和 MIPS32R1：10/10 通过；
- JZ4740 ECC：3/3 通过；
- 发布隐私审计器自身测试：7/7 通过。

浏览器运行时测试要求已有模拟器服务监听 8793；可信 NAND 尚未恢复时不会为了
满足该测试而启动损坏镜像。因此该项留到可信固件重建后的最终联调，不记为前端
代码失败。

随后对便携运行目录做了 PE 正文比对，发现旧 QEMU 目录中的 `libiconv` 已失去
PE 文件头，`libgio/glib/gmodule/gobject/winpthread` 虽保留可解析头部但正文大面积
随机覆盖。新增 `scripts/finalize_x86_64_qemu_runtime.ps1`，从固定 MSYS2 工具链
递归解析并复制 DLL 依赖、校验全部文件为 x86-64、净化路径、审计后再部署。重建后
共 15 个运行文件，在仅含 Windows 系统目录的 PATH 下，QEMU 11.0.0 与 `bbkh1`
机器查询均以退出码 0 完成；未被任何导入表引用的旧 `libslirp-0.dll` 已精确删除。
最终整理脚本固定 `SOURCE_DATE_EPOCH=0`；连续两次从同一构建输入整理得到完全相同的
上述 QEMU SHA-256，确认 strip 和路径净化步骤可复现。

便携 Python 也由 `scripts/finalize_x86_64_python_runtime.ps1` 可复现重建。脚本排除
`__pycache__`、`.pyc/.pyo`、CPython 测试私钥样例、开发工具、上游构建绝对路径和
非前端所需的站点包；首次审计确实拦截了这些内容，未部署失败 staging。第二次结果
为 635 个文件、78 个 x86-64 PE，隔离 PATH 的标准库导入通过，隐私审计 0 命中，
并逐文件清理旧重复标准库 2,605 个文件。启动脚本固定使用 `-B`，避免运行后重新
产生字节码缓存。

## Dingoo A320 输入与运行资源：已恢复

旧 `references/dingoo/firmware/A320_V1.22.rar`、其中的 `a320.HXF`、参考仓库的
17 个 APP 和模拟器中已部署的 13 个 APP 都存在非 NUL 随机覆盖，不能继续使用。
重新从文档固定的官方下载地址取得 V1.22 RAR，并完成以下验收：

- RAR：12,469,522 bytes，SHA-256
  `48010F10E9D9DD695A1A8D048F54EDD6D210858091D47770770189B9DC581795`，
  7-Zip 全量测试通过；
- `a320.HXF`：49,293,334 bytes，SHA-256
  `42FA20327A294ECD5FE95C2F48E5892F4249C475ABC72E16196A334EEBF7DBE8`；
- DingooExtractor 固定上游提交：
  `d9f3e6541f9a205ee675dc676dc9c5ffa859d904`；
- 该提交中的 17 个 APP 与事故前 `app-inventory.json` 的 17 个 SHA-256 逐项一致；
- CCDL/RAWD/符号表解析通过，共 17 款、119 个唯一 imports；
- 部署到模拟器后的 17 个 APP 再次校验清单哈希，隐私审计 0 命中。

`h1-bda-sdk/ports/dingoo_a320/assets/app_manifest.json` 固定源名称、运行时名称、大小
和哈希；`scripts/restore_a320_reference_and_assets.ps1` 在复制前后验证全部输入。
旧参考目录的嵌套 `.git/objects` 本身也损坏，因此恢复脚本不信任该元数据，而是对
32 个上游 tracked 文件做逐文件 SHA-256 比对；嵌套 Git 元数据不会进入发布物。
这项恢复不包括 `KOVH1.PAK`，后者仍必须从用户正版 ROM 重建。

## 仍需重建

- 全树非 NUL 型损坏、丢失目录项和隐私污染复查。
- 从可信固件重建 NAND、系统镜像和最终 x86-64 模拟器。
- 从可信正版卡带备份重建 `KOVH1.PAK` 和实机 KOV 包。

## 必须由用户重新提供的可信输入

- `@ibox H1 V1.41CJXTHF.rar`，可信 SHA-256：
  `B1F5F4D886C1C08C7D6F0722581615A7262CFE44B62F1F1E47EEF204F5E5E5DB`。
- `H1 V1.41SDKHF.rar`，可信 SHA-256：
  `DFEA2563EF6770BA6E30E8006767DB6E7542C59D63CDECD05B266515D94A5A0C`。
- `kov/` 下 7 个正版卡带 ZIP；逐文件可信 SHA-1 见
  `H1项目重建交接说明.txt` 第 2.6 节。

在重新取得并通过归档完整性测试前，当前同名 RAR、ZIP、`KOVH1.PAK`、
`h1-system.raw` 和历史失败 BDA 均不得作为构建输入或发布。

2026-08-04 再次实测，当前两个 RAR 的 SHA-256 分别为
`0FD2ADB0C3AFFD71577CEDF5C6267151661B46A623F888E05B6EB6AF9EA2CBC1` 和
`0F65CF4CC7D4D099376F218A5845F223F548340F528AF5B6969ACC7A5AB63A4A`，与可信
值均不一致。模拟器不得用它们生成或启动正式 NAND。
