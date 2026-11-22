# 变更记录

本文件是 Release 说明的人工摘要来源。每次发布前在“未发布”下写清楚改了什么、
为什么改、哪些边界还没验证；发布时 CI 会把这一节，加上“上一发布 tag 以来”
的真实提交记录，一起写进 GitHub Release。历史发布的具体差异以 Release 页面
和 git 历史为准。

## 未发布

### 1. 项目主页与开发文档

- `README.md` 改为畅行60 当前项目说明（中文）：硬件、已验证功能、安装/更新、
  构建与发布、仓库结构、省电待机、开发约定、已知限制和安全注意事项。
  `README.zh-CN.md` 保留为入口指针，避免两份内容再次分叉。
- 新增 `docs/README.zh-CN.md` 文档索引，按“入门/安装、构建/CI/发布、
  电源/屏幕、蜂窝/网络、存储/UFS、音频/通话、其它机型”分类，说明哪些是
  当前结论、哪些是按日期的取证台账。
- 新增 `docs/POWER-AUDIT-20261122.zh-CN.md`：5G SA 与高速 Wi-Fi 不变的
  前提下，内核/驱动省电审计的实测数据、可行项、不建议项和验证顺序。
- 仓库 About 描述改为当前畅行60 项目说明（中文），不再显示旧的荣悦 E5 文案。

### 2. 发布说明改为“逐次写明改动”

- 新增 `tools/release-changes.py`：从 `CHANGELOG.md` 的“未发布”一节取人工
  摘要，再用 `git log` 汇总上一发布 tag（`changxing60-*`）以来的提交，
  生成 Release 的“本次发布改了什么”。没有上一标签时明确写出，不假装有对比。
- `.github/workflows/changxing60-release.yml` 的 Collect 步调用该工具，
  把结果写入 `release-notes.md`；保留源码提交、内核 release、引导包
  SHA-256、clean base SHA-256 等既有构建元数据。
- 新增 `tools/tests/release-changes.py`，并在 CI 测试步执行。

### 3. 电源：USB3/dwc3 运行时挂起（仅畅行60）

- 实测：dwc3 控制器 `power/control=on`，gadget 为 `not attached` 时仍保持
  active（约 1.26e6 ms active、0 ms suspended）；写 `auto` 后进入
  `suspended`，恢复 `on` 后 active 且累计 29.8 s 挂起时间。USB3 父 glue
  本来就是 `auto`，不能改，它是 5G 数据路径的一部分。
- `e5-power-state` 启动时读取 `/etc/e5/usb-autosuspend`；内容为 `dwc3` 时
  只把 UDC 自己的 `power/control` 从 `on` 改为 `auto`，不碰父 glue。
- 该标记只由 `devices/changxing60/stage.py` 写入，其它机型镜像没有该文件，
  守护进程不做任何修改。IDLE/DEEP 策略、热点和 5G 数据路径不变。
- 未验证边界：插拔数据线能否从 runtime suspend 正常唤醒并重新枚举。
  设备仍有 Wi-Fi/LuCI/SSH 管理通道；若串口控制台异常，先删除
  `/etc/e5/usb-autosuspend` 或把 `power/control` 写回 `on` 复现对照。

### 4. 省电待机现状（本次未改默认值）

- ONLINE → IDLE（关中射频/蓝牙、停 SIM 轮询、保留热点）→ DEEP（关热点 +
  系统挂起）状态机不变；出厂仍是 `idle_min=30`、`deep_min=0`（深睡禁用）。
- 五个系统挂起补丁已在内核准备流程中；畅行60 真机挂起存活、唤醒时延和
  电量收益仍待受控试验。试验步骤见
  `docs/SUSPEND-PATCHES-20261121.zh-CN.md`。
- `clk_summary` 在本机读取会触发 SError 并导致内核 panic；不要用它做省电
  对比，详见 `docs/POWER-AUDIT-20261122.zh-CN.md` 附录。

### 5. 未验证 / 不在本次范围

- 正式刷机、更新、重装、卸载仍标注为 bring-up（`installation_hardware_verified: false`），
  首次更新须有人在场并保持供电。
- dwc3 自动挂起后的数据线热插拔、USB 串口控制台、OTG/扩展坞未在本轮实测。
- VBC/AGDSP、UFS 运行时挂起只记录审计结论，没有改代码：前者缺少安全的
  卸载/空闲路径，后者原厂省电参数已是厂商配置但仍不进入 runtime suspend。
- 蓝牙配对/音频、通话麦克风、最高音量、长期续航等沿用设备台账中的未验收项。

## 2026-11-21

- 系统挂起补丁栈接入（看门狗、DPU、GPU、相机域、原厂时序）；DEEP 的
  看门狗硬阻断解除，`deep_min` 仍为 0。
- 屏幕 pipeline 升级配置迁移；AT 截止时间改用 owner 时钟。

## 2026-11-17

- 分级省电待机 ONLINE → IDLE → DEEP、LuCI/屏幕电源页、更新保留。
- 畅行60 GitHub Actions 内核编译、安装包组装和 Release 流水线。
