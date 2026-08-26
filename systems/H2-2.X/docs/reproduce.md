# H2 V2.2L 本地复现

本文只描述本地复现，不授权重新分发厂商固件或游戏数据。固定输入摘要见 `../inputs.lock.json`，开源组件提交见 `../components.lock.json`。

## 1. 恢复包与基础镜像

下载步步高[官方 H2 V2.2L 超级系统恢复包][firmware]，先核对：

- 字节数：`531645573`
- MD5：`B45752384644F3072C5C94931B000567`
- SHA-256：`2A96F7EF9D8F7CF807E360731225805F621721DCA819F081167389F23A1B25D8`

使用 7-Zip 和 `innoextract` 解包，不运行厂商刷机程序。随后流式构建 2 GiB eMMC：

```powershell
python scripts/build_h2_v2_image.py `
  --input-dir work/h2/pc-installer/app `
  --output emulator/h2/firmware/h2-v2.2l-emmc.raw `
  --manifest work/h2/derived/h2-v2.2l-emmc.json

python scripts/verify_h2_v2_image.py `
  --input-dir work/h2/pc-installer/app `
  --image emulator/h2/firmware/h2-v2.2l-emmc.raw `
  --report work/h2/analysis/h2-image-verification.json
```

基础镜像 SHA-256 为 `7B44B5403EFBB58E6D34F676DE81D251DA6ABF9E0D1502D900E3012759DE40C7`。构建器拒绝覆盖已有镜像。

## 2. ARM64 模拟器

只构建 Windows ARM64。OpenNoah QEMU 固定到 `f29522c83d9aee7b8e2251647363a09a4eea4302`，BootROM 固定到 `2759ce0020c3e823384d82af34741f93ebfbe46e`。最小运行布局为：

```text
emulator/h2/
  bin/windows-arm64/qemu-system-mipsel.exe
  firmware/jz4750l.bin
  firmware/h2-v2.2l-emmc.raw
  share/qemu/keymaps/en-us
  web/h2.html
  web/novnc/...
  h2_emulator.py
  h2.keys
  start-h2.cmd
  start-h2.ps1
```

模拟器写入模式下先应用可逆 WAIT 修正：

```powershell
python systems/H2-2.X/tooling/patch_h2_simulator_idle.py --apply `
  emulator/h2/firmware/h2-v2.2l-emmc.raw `
  --journal work/h2/mission-backup/h2-simulator-idle-undo.json

python systems/H2-2.X/tooling/patch_h2_simulator_idle.py --verify `
  emulator/h2/firmware/h2-v2.2l-emmc.raw
```

该补丁只用于文章 QEMU 缺失的 JZ4750L WAIT 唤醒；物理机镜像不需要它。

## 3. 构建和安装“使命”H2 包装层

以下输入必须来自用户有权使用的本地副本，不能进入源代码发布包：

```powershell
python systems/H2-2.X/tooling/build_h2_mission_loader.py `
  --mission-payload work/h2/mission-input/V1GAME-corrected.BIN `
  --template-bda work/h2/mission-build/中学时间.bda `
  --debug-dir work/h2/mission-debug `
  -o work/h2/mission-build/中学时间-h2.bda

python systems/H2-2.X/tooling/install_h2_mission.py --install `
  --image emulator/h2/firmware/h2-v2.2l-emmc.raw `
  --wrapper work/h2/mission-build/中学时间-h2.bda `
  --payload work/h2/mission-input/V1GAME-corrected.BIN `
  --data work/h2/mission-input/DataLib.dat `
  --index work/h2/mission-input/DataLibIndex.dat `
  --journal work/h2/mission-backup/h2-mission-install-undo.sectors.gz `
  --manifest work/h2/mission-build/h2-mission-install.json `
  --expected-image-sha256 <安装前镜像摘要>
```

安装器只修改精确 FAT 扇区，逐文件回读校验，并生成可恢复安装前摘要的压缩撤销日志。现有 journal/manifest 不会被覆盖。

## 4. 启动与验证

```powershell
python -B emulator/h2/h2_emulator.py --persistent --no-browser --mission-page
```

浏览器访问 `http://127.0.0.1:8797/`。`--mission-page` 使用固定触摸序列停在“更多功能→工具娱乐”的第二页；最后一个时钟图标是当前使命测试入口。不要把模拟器 RAM 提高到 32 MiB 以上。可用以下只读探针核对 stage 和七键事件：

```powershell
python systems/H2-2.X/tooling/probe_h2_mission.py `
  --url http://127.0.0.1:8797 `
  --keys left right volumedown volumeup ret esc
```

## 5. 清理与发布审计

可重下载的编译器缓存、日志、`__pycache__` 和调试 ELF 不得进入发布包。删除前必须解析并核对目标位于 `work/h2`，不要对工作区根目录执行递归删除。

```powershell
python systems/H2-2.X/tooling/cleanup_h2_transients.py
python systems/H2-2.X/tooling/cleanup_h2_transients.py --delete --include-h1-x86
python scripts/build_h2_source_release.py
python scripts/audit_release_secrets.py systems/H2-2.X
python scripts/audit_release_secrets.py emulator/h2
python scripts/audit_release_secrets.py deliverables/bbk-h2-v2.2l-arm64-source-20260826.zip
```

任何用户名、主机名、绝对用户目录、凭据或密钥命中都是发布阻断项。

[firmware]: https://down.eebbk.net/xzzx/h2/%E8%A7%86%E9%A2%91%E5%AD%A6%E4%B9%A0%E6%9C%BA_@iboxH2_V2.2L_%E8%B6%85%E7%BA%A7%E7%B3%BB%E7%BB%9F%E6%81%A2%E5%A4%8D%280002%2920110908084554.rar
