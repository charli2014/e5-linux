# 畅行60（ZTE 7552N / P720S20）OpenWrt 25.12.5 移植

在 Unisoc UMS9620（T760）平台的中兴畅行60 上运行 OpenWrt 25.12.5：
480×854 触摸屏、5G SA 数据、5 GHz 高带宽热点、USB NCM 管理口、
分级省电待机和 GitHub Actions 自动出包。

- 内核：`6.18.54-changxing60-bringup4`（公开供体 `Enceka/linux-lts-e5@020b970e` + 本仓库板级补丁）
- 系统：OpenWrt 25.12.5（armsr/armv8），安装包内含 Windows/macOS/Android 安装器
- 机型标识：`changxing60`；原厂 Android 13
  `ZTE/CN_P720S20/P720S20:13/TP1A.220624.014/20240919.212928:user/release-keys`
- 仓库是 [sprd-linux-devs/e5-linux](https://github.com/sprd-linux-devs/e5-linux) 的 fork；
  荣悦 E5、T551M、M8、K1 等其它机型的资料仍在上游与各自 profile 中

> 这是 bring-up 项目：正式刷机、更新、重装、卸载尚未完成全部硬件组合验收。
> 动手前先读本文的“安装与更新”和“已知限制”，并保留可恢复的 Android 槽位。

## 状态速览

| 项目 | 状态 | 证据/边界 |
|---|---|---|
| 内核与根文件系统启动 | 已实机通过 | 正式安装后正常重启；屏幕、触摸、声卡自动启动 |
| 5G SA 数据 | 已实机通过 | ModemManager/netifd 正常，蜂窝 ICMP 成功；保留 SA 与高速 Wi-Fi 前提 |
| 5 GHz 热点 | 已实机通过 | 信道 149、80 MHz；DHCP/NAT/IPv6 配置完整 |
| 480×854 屏 + AXS15205 触摸 | 已实机通过 | 连续两轮息屏/亮屏、真实滑动坐标；缩放 1.25 |
| 两段式息屏 | 已实机通过 | 背光归零后约 13 秒 `e5-output-ctl status=off` |
| 充电 | 已实机通过 | BQ2560x、0x14 芯片 ID；DCP 常温 2.5 A 为本机策略 |
| 电量计/满充端点 | 部分通过 | 停充/恢复、原厂时间交接通过；完整充放电精度未验收 |
| 音频 | 部分通过 | 媒体、提示音、免提已出声；通话麦克风、最高音量未验收 |
| 蓝牙 | 部分通过 | hci0 与真实扫描通过；配对与音频待验收 |
| USB NCM 管理口 | 已实机通过 | `192.168.9.1`；OTG/扩展坞未覆盖全部物理组合 |
| 分级待机 ONLINE→IDLE | 代码完成，真机 ONLINE 已验证 | IDLE 会关中射频/蓝牙、停 SIM 轮询、保留热点 |
| 深睡 DEEP | 默认禁用（`deep_min=0`） | 挂起补丁已编译；真机挂起存活/唤醒时延/电量收益待受控试验 |
| dwc3 运行时挂起 | 本次新增，待插线唤醒复核 | 仅畅行60 镜像启用；见“省电待机” |
| GitHub Actions 出包 | 已多次发布 | 内核 ~20 分钟，安装包 ~57 分钟，测试在组装前执行 |

完整的设备证据与未验收项见
[devices/changxing60/README.md](devices/changxing60/README.md)。

## 硬件

| 项 | 值 |
|---|---|
| SoC | Unisoc UMS9620（T760），三簇 CPU，Mali-G57 |
| 存储 | UFS，YMTC `YMUS8A1TC2A2C1`，约 119 GiB，4096 字节逻辑块 |
| 原厂布局 | Android userdata 为 FBE+metadata 加密；需在线缩容或经用户确认清空后安装 |
| 显示 | 480×854，两 lane DSI，`lcd_easyquick_aixiesheng_boe_mipi_hd` |
| 触摸 | SPI AXS15205，32 字节报文，固件版本 `0019` |
| 充电 | `ti,bq2560x_chg`，I2C 0x6b，芯片 ID 0x14 |
| 音频 | AW87xxx PA；听筒/免提共用 AOL，按原厂 XML 生成路由与 10 档通话增益 |
| 原厂系统槽位 | 本机 Android 在 B、诊断在 A；工具按当次实机槽位推导，不写死 |

原厂固件、Android vendor 运行库、设备 dump 与 NV 不进入仓库；安装器从**接收方设备**
读取所需内容。仓库里的 `work/`、`dumps/` 是本机取证目录（默认忽略），
不得提交含 IMEI、SN、Wi-Fi 密码或 root 密码的文件。

## 安装与更新

发布页提供完整 ZIP（含安装器、boot、OpenWrt 根文件系统、校验清单）。
安装器只写非当前 Android 槽位，不改 GPT 时优先使用已有未分配空间；
没有空间时必须由用户明确确认后才能处理加密 userdata 和两阶段安装。

1. 备份重要数据，确认设备电量充足，整个过程保持供电。
2. 解压完整发布包，运行根目录的 `OpenWrt-Installer.exe`（Windows）、
   macOS 对应 App，或 Android 安装器。
3. 首次安装按向导创建分区；已有 Linux 系统用“更新 OpenWrt”，
   会保留 `/etc/config`、密码、SSH 密钥、流量记录、用户屏幕应用、NV、
   音频 XML 与触控固件。
4. 更新只允许同内核 release、同 OpenWrt 版本；跨版本先看发布说明。
5. 更新后如需回 Android：Linux shell 执行 `e5-next-boot android` 后重启。

详细边界、槽位同步和回滚证据见
[正式安装接入](docs/CHANGXING60-INSTALL.zh-CN.md)、
[安装与启动回归](docs/INSTALLER-FLOW-AUDIT-20261029.zh-CN.md)、
[在线缩容实测](docs/CHANGXING60-ONLINE-SHRINK-20261029.zh-CN.md)。

> 禁止使用 fastboot。所有刷写走已确认的 ADB/root、安装器或系统内更新通道；
> 通道不可用时保留现场并排查，不换启动协议硬刷。

默认管理地址：热点或 USB 网口 `192.168.9.1`，USB 主机固定 `.9.2`。
首次使用请修改安装器/系统默认密码与热点口令。

## 从源码开发

### 依赖与环境

- Linux 构建机（CI 使用 `ubuntu-24.04-arm`）：`clang lld llvm make bc bison flex
  libssl-dev libelf-dev dwarves gcc-aarch64-linux-gnu cpio lz4 gcc libc6-dev python3`
- 公开内核源码：`Enceka/linux-lts-e5`，默认提交
  `020b970e351eee3887e6caaf2d653926e7086e44`
- 安装器子模块固定为 `kanoqwq/openwrt-tools@57e159c`；
  新检出必须 `--recurse-submodules`
- 构建输入由 `devices/changxing60/ci-seeds/` 与
  `tools/ci-base.lock.json` 锁定；不要用旧包或其它机型文件替代

```sh
git clone --recurse-submodules https://github.com/charli2014/e5-linux.git
cd e5-linux
```

### 运行测试（不接触设备）

```sh
bash -n openwrt/build-rootfs.sh openwrt/device-install-image.sh \
  openwrt/device-install-part.sh openwrt/device-stage-part-update.sh boot/part-update.sh
python3 devices/test_power_state.py
python3 devices/test_staging.py
python3 devices/changxing60/test_screen_defaults.py
python3 openwrt/tests/image-keep-config.py
python3 openwrt/tests/update-device-files.py
python3 tools/tests/ci-release.py
python3 tools/tests/release-changes.py
```

屏幕原生组件、block-mount 等测试需要编译器/容器，CI 在组装前执行完整集合。

### 编译内核

```sh
git clone https://github.com/Enceka/linux-lts-e5
git -C linux-lts-e5 checkout 020b970e351eee3887e6caaf2d653926e7086e44
python3 tools/ci-seeds.py --no-base
python3 devices/changxing60/build-kernel.py \
  --kernel "$PWD/linux-lts-e5" --build "$PWD/out/objects-changxing60" \
  --base-config "$PWD/inputs/ums9620-base.config" \
  --out "$PWD/out/kernel-changxing60" --jobs 4
```

构建器会执行板级准备与 `devices/common/power/` 的五个挂起补丁
（顺序 0001→0002→0004→0005→0006），产出 Image、DTB 与完整模块配套。
内核 release 固定为 `6.18.54-changxing60-bringup4`，重建不变号，
以支持同版本系统内更新。

### 组装发布包

唯一正式入口是 `tools/build-release.py`：

```sh
python3 tools/build-release.py prepare-installers --workspace /path/to/openwrt-build
sudo python3 tools/build-release.py package --workspace /path/to/openwrt-build \
  --profiles changxing60
```

正式产物在 `out/releases/<task>/`，内含唯一 ZIP、`SHA256SUMS` 与
`BUILD-RUN.json`。`.building-*` 是未完成现场，不能发布。
本地固定工作区、缓存和安装器锁的规则见
[本地构建规范](docs/LOCAL-BUILD.zh-CN.md) 与
[Agent 构建手册](docs/AGENT-BUILD.zh-CN.md)；不要复制整份源码/rootfs
或用旧缓存冒充新编译。

### GitHub Actions

工作流：`.github/workflows/changxing60-release.yml`（与上游 E5 的
`release.yml` 独立）。

- 手动：Actions → “Build and publish Changxing 60 OpenWrt” → Run workflow；
  `kernel_ref` 默认登记提交，`publish` 默认开，`prerelease` 默认开。
- 打标签：`git tag changxing60-v<日期> && git push origin changxing60-v<日期>`；
  tag 即 Release 名。
- 手动触发的 Release tag 取 zip 文件名（`r<时间>-g<提交>-s<指纹>`）。
  同一 tag 已发布时拒绝覆盖，需换新 tag。
- `publish` 只在构建、测试和哈希校验通过后创建/发布草稿；
  失败时下载 `cx60-diagnostics-*` 构件排查。

CI 输入是自足的：小件种子在仓库内，clean base 由锁定 Release 分片校验，
补丁 APK 每次用仓库脚本现编。细节见
[CI 编译与发布](docs/CI-CHANGXING60.zh-CN.md)。

## 省电待机

状态机在 `openwrt/overlay/usr/libexec/e5-power-state`，策略文件
`/etc/e5-power.json`，运行状态 `/run/e5-power.json`：

```json
{"idle_min": 30, "deep_min": 0, "hold_awake_min": 5, "inhibit": false}
```

- **ONLINE**：热点、5G、USB 管理口正常，网速不受影响。
- **IDLE**：无 Wi-Fi 客户端、无 USB 数据口且背光关闭达到 `idle_min` 后，
  经 `data-sim` 属主逐卡关射频，停蓝牙与 SIM 轮询，**保留热点**；
  手机重新关联即可唤醒并恢复。关射频前保存恢复标记，避免 IDLE 期间重启
  后以射频关闭状态开机。
- **DEEP**：在 IDLE 基础上再等 `deep_min`，关热点并写 `mem` 挂起。
  出厂 `deep_min=0`（禁用），因为畅行60 真机挂起尚未完成受控验收。
  音频播放、SIPA 内核唤醒锁、升级锁、USB 数据口会阻止 DEEP。
- 短待机被唤醒会翻倍下次计时（封顶 4 倍）；升级或 `inhibit` 立即唤醒；
  守护进程收到 SIGTERM 先恢复射频再退出，强杀也有开机标记兜底。

管理界面：LuCI `admin/modem/power` 与屏幕电源插件共用 `e5-power` rpcd 后端。
`/etc/e5-power.json` 在系统更新时保留。

### 本次新增：dwc3 运行时挂起

实测本机 USB3 控制器在 gadget `not attached` 时仍 `power/control=on`
（约 1.26e6 ms active、0 ms suspended），而父 glue 已是 `auto`。
`devices/changxing60/stage.py` 写入 `/etc/e5/usb-autosuspend`（内容 `dwc3`），
`e5-power-state` 启动时只把 UDC 自己的 `power/control` 改为 `auto`，
不碰承载 5G 数据路径的父 glue；其它机型没有该标记，不受影响。

尚未实测：插数据线能否从 runtime suspend 正常唤醒并重新枚举。
若 USB 串口控制台异常，删除 `/etc/e5/usb-autosuspend` 或把
`/sys/class/udc/*/power/control` 写回 `on` 即可对照；Wi-Fi/LuCI/SSH
始终是另一条管理通道。

### 实测审计与禁区

省电审计（5G SA 与高速 Wi-Fi 不改）的数据、可行项和不建议项见
[省电审计 2026-11-22](docs/POWER-AUDIT-20261122.zh-CN.md)。

> **不要在畅行60 上读 `/sys/kernel/debug/clk/clk_summary`。**
> 本机实测该读取在 `sprd_gate_is_enabled()` 触发 SError，随后内核 panic。
> 需要时钟信息时用构建产物、DT 和驱动代码交叉核对，不做跨电源域裸遍历。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `devices/changxing60/` | 板级 profile、内核准备、充电/音频/触摸适配、CI 种子、离线测试 |
| `devices/common/` | 多机型共享：屏幕、电源状态机、挂起补丁、UFS、网络与 USB 工具 |
| `devices/common/power/` | 五个系统挂起补丁及逐条说明 |
| `openwrt/overlay/` | 设备端根文件系统覆盖层（init 脚本、`e5-power-state`、LuCI/rpcd） |
| `openwrt/build-rootfs.sh` | OpenWrt 根文件系统组装 |
| `tools/` | 发布入口、CI 输入校验、发布说明生成、UFS 身份助手、测试 |
| `.github/workflows/changxing60-release.yml` | 内核编译 → 安装包组装 → 测试 → Release |
| `installer/` | 公共安装器子模块（`kanoqwq/openwrt-tools`，固定提交） |
| `boot/`、`rootfs/`、`kernel/` | 上游 E5 家族的启动、根文件系统与内核构建资料 |
| `docs/` | 按主题与日期组织的证据、设计与操作文档 |
| `work/`、`dumps/` | 本机取证/备份目录，默认忽略，不入库 |

## 文档导航

完整索引见 [docs/README.zh-CN.md](docs/README.zh-CN.md)。建议顺序：

1. 新接手：本文件 → [安装接入](docs/CHANGXING60-INSTALL.zh-CN.md) →
   [CI 编译与发布](docs/CI-CHANGXING60.zh-CN.md)
2. 电源： [待机策略](docs/POWER-STANDBY-20261117.zh-CN.md) →
   [挂起补丁栈](docs/SUSPEND-PATCHES-20261121.zh-CN.md) →
   [省电审计](docs/POWER-AUDIT-20261122.zh-CN.md)
3. 存储： [UFS 适配指南](docs/UFS-PORTING.zh-CN.md)（改 UFS 前必读）
4. 构建： [本地构建规范](docs/LOCAL-BUILD.zh-CN.md) →
   [Agent 构建手册](docs/AGENT-BUILD.zh-CN.md)
5. 原厂行为与新机型： [原厂适配检查表](docs/NEW-DEVICE-STOCK-ADAPTATION.zh-CN.md)、
   [原厂充电/通话/Wi-Fi 证据](docs/STOCK-CHARGE-CALL-WIFI-20261016.zh-CN.md)

日期命名的文档是当时的取证台账，结论可能后来被修正；当前状态以本文件、
各主题最新文档和 git 历史为准。

## 发布流程与变更说明

- 每次发布前在 [CHANGELOG.md](CHANGELOG.md) 的“未发布”一节写清楚：
  改了什么、为什么、已验证/未验证边界、回滚方式。
- 构建时 `tools/release-changes.py` 会把该节与“上一发布 tag 以来”的
  git 提交记录合成为 Release 的“本次发布改了什么”，再附源码提交、
  内核 release、引导包与 clean base 的 SHA-256。
- 没有上一发布标签时会明确写出“无法自动对比”，不伪造差异。
- 发布为草稿 → 校验资产哈希 → 上传 → 正式发布；已发布 tag 不覆盖。

## 开发约定

- `AGENTS.md` 是协作规则的权威版本，提交前先读。要点：
  - NR0/AT 通道只有一个属主；不要在其它服务里抢 URC。
  - 改 UFS 前先读 `docs/UFS-PORTING.zh-CN.md`；单位、GPT、身份与加密
    边界不能用“看起来能读”代替验收。
  - 原厂固件/驱动是参照，不以另一机型的 GPL 代码推断本机事实。
  - 每个结论区分“原厂证据 / 源码 / 编译 / 只读启动 / 完整系统 / 长期验收”。
  - `tools/build-release.py` 是唯一发布入口；安装器子模块由上游维护，
    本仓库只更新 gitlink 与版本锁。
  - 不自动删除缓存、dump、备份或历史发布；不创建项目外目录。
- 新增板级动作优先放进 `devices/changxing60/stage.py` 或板级准备脚本，
  共享层只放经过多机型验证的能力。
- 设备端测试先装试验版，用户确认后再提交；提交信息说明验证范围。

## 已知限制

- 正式安装/更新/重装/卸载的全部硬件组合未验收；`profile.json` 仍保留
  `installation_hardware_verified: false`。
- 深睡默认关闭；挂起补丁的畅行60 真机收益与唤醒时延未测。
- dwc3 自动挂起后的数据线热插拔/串口控制台未实测。
- 蓝牙配对/音频、通话麦克风、最高音量、长期续航、外接充电器与
  OTG/扩展坞组合仍有未验收项。
- 内核供体是公开的 UMS9620 基线，不是本机原厂 5.4 源码；行为差异按
  “原厂证据优先”逐项核对。
- 读取 `clk_summary` 会 panic（见上文），不要用于功耗排查。

## 许可与致谢

- 内核：公开 `Enceka/linux-lts-e5`（GPL-2.0）；挂起补丁参考
  `CharlesGool/e5-sleep-kernel`（GPL-2.0）。
- 仓库脚本与文档：MIT，见 [LICENSE](LICENSE)。
- 安装器：[kanoqwq/openwrt-tools](https://github.com/kanoqwq/openwrt-tools)，
  本仓库以子模块固定提交引用。
- 上游机型与移植方法：[sprd-linux-devs/e5-linux](https://github.com/sprd-linux-devs/e5-linux)。
- 原厂固件、Android vendor 组件与 bootloader 归各自权利人所有，
  不在本仓库分发。

旧链接 [README.zh-CN.md](README.zh-CN.md) 保留为指向本文件的说明，避免两份内容分叉。
