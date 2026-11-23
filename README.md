# 畅行60（ZTE 7552N / P720S20）OpenWrt 25.12.5 移植

在中兴畅行60（Unisoc UMS9620 / T760，UFS 存储）上运行 **OpenWrt 25.12.5**，支持 480×854 触摸屏、5G SA 数据、5 GHz 热点、USB NCM 有线管理口、两段式息屏、分级省电待机（ONLINE → IDLE → DEEP）以及 GitHub Actions 自动构建发布。

- **内核版本**：`6.18.54-changxing60-bringup4`
- **系统版本**：OpenWrt 25.12.5（`armsr/armv8`）
- **原厂参考固件**：`ZTE/CN_P720S20/P720S20:13/TP1A.220624.014/20240919.212928:user/release-keys`
- **最新正式安装包**：见 [GitHub Releases](https://github.com/charli2014/e5-linux/releases)

> **重要提醒**
> - 本项目仍处于 bring-up 阶段，动手刷机前请完整阅读下方“怎么安装到手机上”与“已知限制”，并保留可回退的 Android 槽位。
> - **严禁使用 `fastboot` 刷写**，全部安装与更新请通过安装包自带工具或系统内更新通道完成。

---

## 一、参考与致谢项目

本仓库基于以下开源项目构建和适配，向各上游作者致谢：

| 项目 | 角色与用途 | 说明 |
| :--- | :--- | :--- |
| [sprd-linux-devs/e5-linux](https://github.com/sprd-linux-devs/e5-linux) | **本仓库上游 Fork** | 提供展锐平台 OpenWrt 移植框架、ModemManager/BlueZ/hostapd 补丁、双卡与屏幕基础架构以及 E5/T551M/M8/K1 等机型资料（MIT） |
| [Enceka/linux-lts-e5](https://github.com/Enceka/linux-lts-e5) | **内核源码供体** | 提供 UMS9620 Linux 6.18.54 基线源码，当前固定提交 `020b970e351eee3887e6caaf2d653926e7086e44`（GPL-2.0） |
| [CharlesGool/e5-sleep-kernel](https://github.com/CharlesGool/e5-sleep-kernel) | **深度挂起补丁参考** | 提供 UMP9620 看门狗跨挂起、DPU、GPU 与相机域断电等系统挂起补丁参考（GPL-2.0） |
| [kanoqwq/openwrt-tools](https://github.com/kanoqwq/openwrt-tools) | **跨平台安装器** | 以 Git 子模块 `installer/`（固定提交 `57e159c`）引用，提供 Windows / macOS / Android 图形与命令行安装器 |

> 原厂固件、Android vendor 运行库、设备 dump 与 NV 均**不在本仓库分发**；安装器会在刷机时直接从目标手机读取所需原厂资源。

---

## 二、本项目做了哪些修改

相对上游 `sprd-linux-devs/e5-linux`，本仓库针对**畅行60（`changxing60`）**主要完成了以下适配、省电优化与实机缺陷修复：

### 1. 畅行60 硬件与基础系统适配
- **显示与触控**：适配 480×854 两 lane DSI 屏幕与 SPI AXS15205 触摸芯片，屏端界面默认缩放 `1.25`，锁屏显示在线设备数。
- **电源与充电**：适配 `ti,bq2560x_chg`（I2C `0x6b`，芯片 ID `0x14`）、网页限充/停充策略与原厂电量时间交接。
- **音频与存储**：适配 AW87xxx 功放与按原厂 XML 生成的音频路由/通话增益；适配 119 GiB UFS（4096 字节逻辑块）的在线 F2FS 缩容、安装与系统内更新启动链。
- **网络**：支持 5G SA 数据、5 GHz（80 MHz，1×1 Wi-Fi 5）热点及 USB NCM 管理口。

### 2. 分级省电与系统挂起
- **两段式息屏**：息屏先关背光，默认 10 秒后通过 `e5-output-ctl` 关闭整条显示管线（DPU/DSI 进入 `suspended`），亮屏时先恢复管线再开背光；升级迁移脚本保证老配置自动补齐默认值。
- **三级待机状态机（`e5-power-state`）**：
  - `ONLINE`：热点、5G、USB 全速在线；
  - `IDLE`：无已认证 Wi-Fi 客户端、无 USB 数据连接且背光关闭达到 `idle_min` 后，关闭蜂窝射频/蓝牙/SIM 轮询，**保留热点**，客户端关联或亮屏即唤醒；
  - `DEEP`：在 `IDLE` 后继续等待 `deep_min`，关闭热点并执行内核 `mem` 挂起（出厂默认 `deep_min=0` 禁用，可在 LuCI `admin/modem/power` 或屏端电源插件中按需开启）。
- **内核挂起与外设省电**：接入 5 个系统挂起内核补丁（`devices/common/power/`）；开启 `workqueue.power_efficient=1`；仅在畅行60 启动时将闲置 USB3 `dwc3` 控制器设为 `power/control=auto`（不触碰承载 5G 数据路径的父 glue）。

### 3. 基带、休眠唤醒与系统稳定性修复
- **独立 AT 通道分流修复**（`rootfs/overlay/opt/e5/e5-at`）：补齐 `changxing60` / `y60` 到 `t551m-atd`（`nr2/nr6/nr7`）分流白名单，消除开机时 `boot-replay early` 与 `ModemManager` 互相等待导致的 **90 秒死锁超时** 以及后台 `Lock state unavailable` 提示（实测开机锁网重放降至 0.81 秒，5G 约 15 秒拨通）。
- **单卡休眠唤醒防基带复位**（`data-sim`、`e5-power-state`）：下发 `SFUN=4/5` 前先用 `+CPIN?` 探测空卡槽，跳过 `+CME ERROR: 10`（无卡）槽位，避免空 SIM 槽启动协议栈引发 5G 基带复位与 AT 通道隔离；同时射频恢复改为逐槽记录进度、失败保留标记并自动重试。
- **防未认证设备误唤醒**（`e5-power-state`）：`clients()` 仅统计 `authorized: true` 的已认证客户端，忽略密码错误等未完成握手的临时关联。
- **BusyBox 兼容性修复**（`ttl-engine`）：将不兼容的 `flock -w 10` 改为 `flock -n` 重试循环，修复开机与 `ifup wan` 时的 TTL 应用失败报错。

### 4. 独立 CI 构建与发布说明自动化
- 新增自足的 `.github/workflows/changxing60-release.yml`（不依赖上游 E5 流水线），在组装前自动运行单元测试与输入校验。
- 新增 `tools/release-changes.py`，自动合并 `CHANGELOG.md` 摘要与上一发布以来的提交记录生成 Release 说明。

### 当前功能验证状态

| 模块 | 状态 | 说明与边界 |
| :--- | :--- | :--- |
| 启动 / 5G SA / 5 GHz 热点 / USB NCM | 已实机通过 | 开机约 15 秒 5G 拨通，锁网缓存自动就绪 |
| 480×854 屏幕 + 触摸 + 两段息屏 | 已实机通过 | 息屏后 DPU/DSI 正常进入 `suspended` |
| 充电与限充保护 | 已实机通过 | BQ2560x 正常充停；完整充放电精度待长期验收 |
| ONLINE → IDLE → DEEP 休眠与唤醒 | 单卡已实机验证 | 实测连续 4 次真实 DEEP 挂起/唤醒均在 5–7 秒恢复 5G；插充电器时受内核 6 秒充电监测定时器影响会周期唤醒，纯电池整夜长睡耗时待统计 |
| USB `dwc3` 运行时挂起 | 已启用，待复核 | 插拔数据线唤醒与 USB 串口控制台未完全实测 |
| 音频 / 蓝牙 | 部分通过 | 外放/提示音、蓝牙扫描已通过；通话麦克风、蓝牙配对音频待验收 |

---

## 三、怎么安装到手机上

### 刷机前准备
1. **备份手机重要数据**，确保电量充足（建议 ≥ 50%），整个安装/更新过程保持供电。
2. 前往 [Releases 页面](https://github.com/charli2014/e5-linux/releases) 下载最新的 `changxing60-openwrt-*.zip` 完整发布包并解压。
3. 手机需已具备可用的 root / ADB 环境（原厂 Android 槽位会被保留用于回退）。

### 方式 A：首次安装到畅行60
1. 将手机通过 USB 连接到电脑，确保 `adb` 已识别设备。
2. 运行解压目录中的安装器：
   - **Windows**：双击 `OpenWrt-Installer.exe`
   - **macOS / Android**：使用包内对应平台安装器
3. 按安装器向导操作：
   - 安装器会自动推导当前 Android 槽位，**只写入非当前 Android 槽位**；
   - 优先使用已有未分配空间；若空间不足，需经你明确确认后执行加密 `userdata` 在线缩容或两阶段安装。
4. 安装完成后按提示重启，即可进入 OpenWrt。

### 方式 B：已有畅行60 OpenWrt 系统升级
1. 电脑连接手机热点或 USB 网口，确保能访问 `192.168.9.1`。
2. 打开新版本发布包内的安装器，选择 **“更新 OpenWrt”**（或命令行 `--update`）。
3. 更新会自动保留：`/etc/config`、登录密码、SSH 密钥、流量记录、用户屏幕应用、`/etc/e5-power.json`、NV、音频 XML 与触控固件。
4. **注意**：系统内更新仅支持**同内核 release 与同 OpenWrt 版本**；跨大版本请先看对应 Release 说明。

### 刷机后常用入口与回退
- **管理后台（LuCI）**：浏览器访问 `http://192.168.9.1`（热点或 USB 网口均可用，USB 主机侧固定为 `192.168.9.2`）。
- **SSH 登录**：`ssh root@192.168.9.1`（首次使用请务必修改 root 密码和 Wi-Fi 密码）。
- **切回原厂 Android**：在手机 SSH 终端执行 `e5-next-boot android` 后执行 `reboot` 即可。

---

## 四、文档怎么看

本仓库的文档分为两类：**当前有效文档**（随代码持续更新）和**带日期的取证台账**（记录当时的排查证据与中间过程，结论可能被后续改动更新）。完整目录见 [docs/README.zh-CN.md](docs/README.zh-CN.md)。

按你的目的选择阅读路线即可：

1. **只想刷机 / 更新 / 回退 Android**
   - 本页“怎么安装到手机上” → [正式安装接入](docs/CHANGXING60-INSTALL.zh-CN.md) → [在线缩容实测](docs/CHANGXING60-ONLINE-SHRINK-20261029.zh-CN.md) → [安装流程审计](docs/INSTALLER-FLOW-AUDIT-20261029.zh-CN.md)
2. **想调省电 / 启用深度休眠（DEEP）/ 查发热原因**
   - [分级省电待机设计](docs/POWER-STANDBY-20261117.zh-CN.md) → [系统挂起补丁与受控试验](docs/SUSPEND-PATCHES-20261121.zh-CN.md) → [内核/驱动省电审计](docs/POWER-AUDIT-20261122.zh-CN.md) → [畅行60 CPU 与调压依据](devices/changxing60/CPU-POWER.zh-CN.md)
3. **想自己编译内核、打包或走 GitHub Actions 发布**
   - [CI 编译与发布](docs/CI-CHANGXING60.zh-CN.md) → [本地构建规范](docs/LOCAL-BUILD.zh-CN.md) → [Agent 构建手册](docs/AGENT-BUILD.zh-CN.md) → [变更记录](CHANGELOG.md)
4. **想做二次开发、查硬件细节或适配新机型**
   - [协作与红线规则](AGENTS.md) → [畅行60 硬件适配台账](devices/changxing60/README.md) → [UFS 适配指南（改存储前必读）](docs/UFS-PORTING.zh-CN.md) → [新机型原厂行为检查表](docs/NEW-DEVICE-STOCK-ADAPTATION.zh-CN.md)

---

## 五、源码获取与构建速查

```sh
# 必须递归拉取 installer 子模块
git clone --recurse-submodules https://github.com/charli2014/e5-linux.git
cd e5-linux
```

- **离线回归测试**（Linux / WSL）：
  ```sh
  python3 devices/test_power_state.py
  python3 devices/t551m/test_at_routing.py
  python3 openwrt/tests/sim-radio.py
  python3 tools/tests/ci-release.py
  python3 tools/tests/release-changes.py
  ```
- **GitHub Actions 自动构建**：进入仓库 **Actions → Build and publish Changxing 60 OpenWrt → Run workflow**；如需发布正式版本（非 pre-release），请取消勾选 `prerelease`。详细本地编译与打包命令见 [CI 编译与发布](docs/CI-CHANGXING60.zh-CN.md) 和 [本地构建规范](docs/LOCAL-BUILD.zh-CN.md)。

### 仓库核心目录

| 目录 | 说明 |
| :--- | :--- |
| `devices/changxing60/` | 畅行60 板级配置、内核准备、充电/音频/触摸适配与 CI 种子 |
| `devices/common/` | 多机型共享的屏幕、电源与系统挂起补丁（`devices/common/power/`） |
| `openwrt/` | OpenWrt 根文件系统组装脚本、overlay（`e5-power-state` 等）、LuCI 应用与测试 |
| `rootfs/overlay/opt/e5/` | 设备端核心工具（如 `e5-at`） |
| `installer/` | 跨平台安装器子模块（`kanoqwq/openwrt-tools`） |
| `tools/` | 正式构建与发布入口（`build-release.py`、`release-changes.py`、CI 校验） |
| `docs/` | 专题文档与硬件取证台账（索引见 [docs/README.zh-CN.md](docs/README.zh-CN.md)） |

---

## 六、已知限制与硬件禁区

- **硬件禁区**：**不要读取畅行60 的 `/sys/kernel/debug/clk/clk_summary`**，本机实测跨电源域读取时钟门控寄存器会触发 SError 并导致内核 panic。
- **深睡提示**：`deep_min` 出厂默认 `0`（禁用）；插着充电器进入 DEEP 时会被展锐充电管理驱动的 ~6 秒定时唤醒叫醒，纯电池待机长睡续航仍待更多用户长期实测。
- **未完全验收项**：全量硬件组合下的安装/重装/卸载、dwc3 自动挂起后的插线热唤醒/串口控制台、通话麦克风、蓝牙音频与 OTG 扩展坞组合。

> 旧链接 [README.zh-CN.md](README.zh-CN.md) 保留为指向本文件的入口指针；协作开发规范请以 [AGENTS.md](AGENTS.md) 为准。
