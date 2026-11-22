# 文档索引

本仓库的文档分两类：

- **当前结论**：项目主页、安装接入、CI、待机策略、UFS 指南等，随代码更新。
- **取证台账**：文件名带日期的记录，写的是当时看到了什么、试过什么、
  哪些被否定。结论可能后来被修正；判断现状时以最新主题文档和 git 历史为准。

项目总览从 [README.md](../README.md) 开始。

## 入门与安装

| 文档 | 用途 |
|---|---|
| [CHANGXING60-INSTALL.zh-CN.md](CHANGXING60-INSTALL.zh-CN.md) | 正式安装接入、公共存储约定、本机资源与验收边界 |
| [INSTALLER-FLOW-AUDIT-20261029.zh-CN.md](INSTALLER-FLOW-AUDIT-20261029.zh-CN.md) | 安装器流程审计与正式启动回归 |
| [CHANGXING60-ONLINE-SHRINK-20261029.zh-CN.md](CHANGXING60-ONLINE-SHRINK-20261029.zh-CN.md) | 加密 F2FS 保数据在线缩容、备份与重启核验 |
| [ONLINE-F2FS-INSTALL-20261029.zh-CN.md](ONLINE-F2FS-INSTALL-20261029.zh-CN.md) | 在线 F2FS 安装工具与硬件边界 |
| [ONLINE-F2FS-REINSTALL-20261030.zh-CN.md](ONLINE-F2FS-REINSTALL-20261030.zh-CN.md) | 重装路径与保留项 |
| [UPDATE-STAGING-20261025.zh-CN.md](UPDATE-STAGING-20261025.zh-CN.md) | 系统内更新暂存与切换 |
| [UNINSTALL-PRESERVE-20261030.zh-CN.md](UNINSTALL-PRESERVE-20261030.zh-CN.md) | 卸载时保留与恢复规则 |
| [BOOT-SLOT-ROLES-20261020.zh-CN.md](BOOT-SLOT-ROLES-20261020.zh-CN.md) | Android/Linux 槽位角色与试启动 |
| [UFS-UPDATE-BOOT-20261030.zh-CN.md](UFS-UPDATE-BOOT-20261030.zh-CN.md) | UFS 机型的更新启动链 |
| [INSTALLER-SUBMODULE.zh-CN.md](INSTALLER-SUBMODULE.zh-CN.md) | 安装器子模块与版本锁 |

## 构建、CI 与发布

| 文档 | 用途 |
|---|---|
| [CI-CHANGXING60.zh-CN.md](CI-CHANGXING60.zh-CN.md) | Actions 流水线、自足输入、触发方式、产物与约束 |
| [LOCAL-BUILD.zh-CN.md](LOCAL-BUILD.zh-CN.md) | 本地固定工作区、分阶段构建、打包与失败处理 |
| [AGENT-BUILD.zh-CN.md](AGENT-BUILD.zh-CN.md) | Agent 本机操作手册（Windows/WSL/安装器） |
| [RELEASE.md](RELEASE.md) | 上游 E5 发布流程（与畅行60 独立） |
| [RELEASE-INDEX-CLI.zh-CN.md](RELEASE-INDEX-CLI.zh-CN.md) | 发布索引工具 |
| [RELEASE-UI-CLEANUP-20261029.zh-CN.md](RELEASE-UI-CLEANUP-20261029.zh-CN.md) | 发布界面整理 |
| [KERNEL-RELEASE-NAMING-20261018.zh-CN.md](KERNEL-RELEASE-NAMING-20261018.zh-CN.md) | 内核 release 命名规则 |
| [../CHANGELOG.md](../CHANGELOG.md) | 每次发布的人工摘要来源 |
| [../tools/release-changes.py](../tools/release-changes.py) | 发布说明生成器（摘要 + 提交记录） |

## 电源、待机与屏幕

| 文档 | 用途 |
|---|---|
| [POWER-STANDBY-20261117.zh-CN.md](POWER-STANDBY-20261117.zh-CN.md) | ONLINE→IDLE→DEEP 状态机、界面、更新保留与验证状态 |
| [SUSPEND-PATCHES-20261121.zh-CN.md](SUSPEND-PATCHES-20261121.zh-CN.md) | 五个挂起补丁、接线、受控试验步骤 |
| [POWER-AUDIT-20261122.zh-CN.md](POWER-AUDIT-20261122.zh-CN.md) | 5G SA/Wi-Fi 不变前提下的内核/驱动省电审计 |
| [POWER-SAVING-20261024.zh-CN.md](POWER-SAVING-20261024.zh-CN.md) | 前序息屏/轮询优化 |
| [POWER-PROBE-20261031.zh-CN.md](POWER-PROBE-20261031.zh-CN.md) | 功耗探针与采样方法 |
| [POWER-REGISTRATION-20261101.zh-CN.md](POWER-REGISTRATION-20261101.zh-CN.md) | 功耗登记项 |
| [CPU0-IDLE-SWITCH-20261024.zh-CN.md](CPU0-IDLE-SWITCH-20261024.zh-CN.md) | CPU0 idle 切换 |
| [SCREEN-POWER-EVENTS-20261012.zh-CN.md](SCREEN-POWER-EVENTS-20261012.zh-CN.md) | 屏幕电源事件 |
| [SCREEN-NATIVE-20261023.zh-CN.md](SCREEN-NATIVE-20261023.zh-CN.md) | 原生屏幕观察器 |
| [SCREEN-FLUIDITY-20261027.zh-CN.md](SCREEN-FLUIDITY-20261027.zh-CN.md) | 屏幕流畅度 |
| [SCREEN-SHARED-LAYOUT-20261027.zh-CN.md](SCREEN-SHARED-LAYOUT-20261027.zh-CN.md) | 共享屏幕布局 |
| [../devices/changxing60/CPU-POWER.zh-CN.md](../devices/changxing60/CPU-POWER.zh-CN.md) | 本机三簇 CPU、频点、调压与温控依据 |

> **禁区**：不要读取畅行60 的 `/sys/kernel/debug/clk/clk_summary`，本机实测会
> 触发 SError 并 panic。原因与替代取证方法见省电审计附录。

## 蜂窝、网络与 Wi-Fi

| 文档 | 用途 |
|---|---|
| [CHANGXING60-SIM-ACTIVATION-20261101.zh-CN.md](CHANGXING60-SIM-ACTIVATION-20261101.zh-CN.md) | 本机 SIM 激活与运营商显示 |
| [SIM-RADIO-SFUN-20261019.zh-CN.md](SIM-RADIO-SFUN-20261019.zh-CN.md) | 射频开关的 SFUN 属主 |
| [DATA-SIM-ADOPT-20261114.zh-CN.md](DATA-SIM-ADOPT-20261114.zh-CN.md) | 数据卡选择与持久化 |
| [DUAL-SIM-BOOT-EMMC-20261014.zh-CN.md](DUAL-SIM-BOOT-EMMC-20261014.zh-CN.md) | 双卡启动 |
| [SIPA-DATA-PATH-20261015.zh-CN.md](SIPA-DATA-PATH-20261015.zh-CN.md) | SIPA 数据路径 |
| [SIPA-TX-WAKE-20261106.zh-CN.md](SIPA-TX-WAKE-20261106.zh-CN.md) | SIPA 发送唤醒与挂起门 |
| [SIPA-BUFFER-LIFECYCLE-20261114.zh-CN.md](SIPA-BUFFER-LIFECYCLE-20261114.zh-CN.md) | SIPA 缓冲区生命周期 |
| [CELLULAR-RA-RENEW-20261106.zh-CN.md](CELLULAR-RA-RENEW-20261106.zh-CN.md) | 蜂窝 RA/DNS 续期 |
| [NETWORK-PERFORMANCE-20261026.zh-CN.md](NETWORK-PERFORMANCE-20261026.zh-CN.md) | 网络性能与恢复 |
| [TTL-FLOW-OFFLOAD-20261106.zh-CN.md](TTL-FLOW-OFFLOAD-20261106.zh-CN.md) | TTL 与 flow offload |
| [WIFI-AP-SCAN-20261111.zh-CN.md](WIFI-AP-SCAN-20261111.zh-CN.md) | AP 扫描补丁 |
| [WIFI-CHANLIST-20261109.zh-CN.md](WIFI-CHANLIST-20261109.zh-CN.md) | 信道列表 |
| [WIFI-BA-RECOVERY-20261030.zh-CN.md](WIFI-BA-RECOVERY-20261030.zh-CN.md) | Block-ACK 恢复 |
| [WIFI-CX60-ONEPLUS11-20261030.zh-CN.md](WIFI-CX60-ONEPLUS11-20261030.zh-CN.md) | 本机与 OnePlus 11 的 Wi-Fi 对照 |
| [WPA3-COMPATIBILITY-20261015.zh-CN.md](WPA3-COMPATIBILITY-20261015.zh-CN.md) | WPA3/SAE 兼容 |
| [../openwrt/MULTISIM.md](../openwrt/MULTISIM.md) | OpenWrt 双卡 API 与界面 |

## 存储、UFS 与 NV

| 文档 | 用途 |
|---|---|
| [UFS-PORTING.zh-CN.md](UFS-PORTING.zh-CN.md) | 新机型 UFS 适配方法（改 UFS 前必读） |
| [INSTALLER-UFS-REGRESSION-20261029.zh-CN.md](INSTALLER-UFS-REGRESSION-20261029.zh-CN.md) | UFS 安装器回归 |
| [NV-PERSISTENCE.zh-CN.md](NV-PERSISTENCE.zh-CN.md) | NV 持久化与只读工作副本 |
| [INTERNAL-PARTITION-SYSTEM-20261012.zh-CN.md](INTERNAL-PARTITION-SYSTEM-20261012.zh-CN.md) | 内置分区与安装布局 |
| [SML-VOLTAGE-COMPATIBILITY.zh-CN.md](SML-VOLTAGE-COMPATIBILITY.zh-CN.md) | 本机 SML 电压表匹配 |
| [UFS-UPDATE-BOOT-20261030.zh-CN.md](UFS-UPDATE-BOOT-20261030.zh-CN.md) | UFS 更新启动链 |
| [UPDATE-NV-RETRY-20261030.zh-CN.md](UPDATE-NV-RETRY-20261030.zh-CN.md) | 更新时的 NV 重试 |

## 音频、通话与通知

| 文档 | 用途 |
|---|---|
| [RINGTONES-NOTIFICATIONS.zh-CN.md](RINGTONES-NOTIFICATIONS.zh-CN.md) | 铃声与通知音 |
| [INCOMING-CALL-ALERTS.zh-CN.md](INCOMING-CALL-ALERTS.zh-CN.md) | 来电提醒 |
| [VOICE-IMS-URC-20261010.zh-CN.md](VOICE-IMS-URC-20261010.zh-CN.md) | IMS 语音 URC |
| [VOICE-ACCEPT-FAILURE-20261020.zh-CN.md](VOICE-ACCEPT-FAILURE-20261020.zh-CN.md) | 接听失败排查 |
| [SMS-MULTIPART-FIX.zh-CN.md](SMS-MULTIPART-FIX.zh-CN.md) | 长短信 |
| [SMS-FORWARD-PORT.zh-CN.md](SMS-FORWARD-PORT.zh-CN.md) | 短信转发 |
| [SMS-SLOT-RECEPTION-20261109.zh-CN.md](SMS-SLOT-RECEPTION-20261109.zh-CN.md) | 双卡短信接收 |
| [STOCK-CHARGE-CALL-WIFI-20261016.zh-CN.md](STOCK-CHARGE-CALL-WIFI-20261016.zh-CN.md) | 原厂充电/通话/Wi-Fi 证据 |
| [../devices/changxing60/README.md](../devices/changxing60/README.md) | 本机音频、触摸、显示逐轮适配记录 |

## 电池与充电

| 文档 | 用途 |
|---|---|
| [BATTERY-NATIVE-CHECKPOINT-20261031.zh-CN.md](BATTERY-NATIVE-CHECKPOINT-20261031.zh-CN.md) | 电量基准与原厂时间交接 |
| [BATTERY-BOOT-OCV-20261031.zh-CN.md](BATTERY-BOOT-OCV-20261031.zh-CN.md) | 开机 OCV |
| [BATTERY-HISTORY-20261103.zh-CN.md](BATTERY-HISTORY-20261103.zh-CN.md) | 电量历史 |
| [BATTERY-SOC-STALL-20261030.zh-CN.md](BATTERY-SOC-STALL-20261030.zh-CN.md) | SOC 停滞 |
| [FGU-FULL-CHARGE-20261016.zh-CN.md](FGU-FULL-CHARGE-20261016.zh-CN.md) | 满充端点 |
| [FGU-SOC-RESTORE-20261015.zh-CN.md](FGU-SOC-RESTORE-20261015.zh-CN.md) | SOC 恢复 |
| [WEB-CHARGING-20261016.zh-CN.md](WEB-CHARGING-20261016.zh-CN.md) | 网页限充 |
| [LOW-BATTERY-STOCK-20261018.zh-CN.md](LOW-BATTERY-STOCK-20261018.zh-CN.md) | 低电量原厂行为 |
| [../devices/changxing60/CHARGER-VARIANTS-20261101.zh-CN.md](../devices/changxing60/CHARGER-VARIANTS-20261101.zh-CN.md) | 本机充电器变体 |

## 其它机型与通用方法

| 文档 | 用途 |
|---|---|
| [NEW-DEVICE-STOCK-ADAPTATION.zh-CN.md](NEW-DEVICE-STOCK-ADAPTATION.zh-CN.md) | 新机型原厂行为检查表 |
| [../devices/t551m/README.md](../devices/t551m/README.md) | T551M |
| [../devices/m8/README.md](../devices/m8/README.md) | M8 家族 |
| [../devices/lym10k/README.md](../devices/lym10k/README.md) | 岭燕 LYM-10K |
| [../devices/k1/README.md](../devices/k1/README.md) | angelcare K1 |
| [../devices/yuanhang41s/README.md](../devices/yuanhang41s/README.md) | 远航 41S |
| [FINDINGS.md](FINDINGS.md) | 上游荣悦 E5 的测量记录，**不是畅行60 证据** |
| [STATUS.md](STATUS.md) | 上游工作清单 |

## 取证与提交约定

- `work/`、`dumps/` 只在本地保留原始日志、备份和含敏感标识的现场；
  不提交 IMEI、SN、Wi-Fi 密码、root 密码或原始 NV。
- 日期文档里的“已通过”只覆盖当次测试条件；跨机型、跨内核或跨硬件组合
  必须重新验收。
- 结论按“原厂证据 / 源码 / 编译 / 只读启动 / 完整系统 / 长期硬件验收”
  分层记录，不把编译通过或菜单可选当成功能验收。
- 改动、验证范围与回滚方式写进 [CHANGELOG.md](../CHANGELOG.md) 的
  “未发布”，发布时自动进入 Release 说明。
