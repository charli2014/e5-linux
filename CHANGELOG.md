# 变更记录

本文件是 Release 说明的人工摘要来源。每次发布前在“未发布”下写清楚改了什么、
为什么改、哪些边界还没验证；发布时 CI 会把这一节，加上“上一发布 tag 以来”
的真实提交记录，一起写进 GitHub Release。历史发布的具体差异以 Release 页面
和 git 历史为准。

## 未发布

### 1. 新增“仅连接设备时开启基带”按需联网省电选项（畅行60 默认开启）

- `openwrt/overlay/usr/libexec/e5-power-state`：新增 `wake_on_client` 策略项（畅行60 在 `/usr/share/e5-power/defaults.json` 中默认开启 `true`；老配置升级缺失该字段时自动继承板级默认值，用户手动关闭则严格保留）。
  - 从 `DEEP` 深度休眠唤醒时，若无已认证 Wi-Fi 客户端或 USB 数据设备连接，仅恢复 Wi-Fi 热点等待连接，**保持在 `IDLE` 浅待机，不提前拉起 5G 基带、蓝牙与 SIM 轮询**。
  - 在 `IDLE` 状态下仅按电源键亮屏查看时间/电量时，不唤醒基带联网（同时暂停 `DEEP` 倒计时避免看屏途中息屏挂起）；直到有已认证 Wi-Fi 客户端关联、插上 USB 数据口、或用户手动打开射频/勾选“保持唤醒”时，才立即恢复基带并拨号联网。
- `openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/power-control` & `devices/common/infoscreen/power/backend.uc`：后端校验与配置合并同步支持 `wake_on_client`。
- `openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/power.js` & `devices/common/infoscreen/power/power.js`：LuCI 网页端（`admin/modem/power`）与手机屏端电源设置页同步增加“仅连接设备时开启基带”开关，保存后即时生效。

### 2. 防未认证 Wi-Fi 设备误唤醒待机

- `openwrt/overlay/usr/libexec/e5-power-state`：`clients()` 改为仅统计 `authorized: true` 的已认证客户端，忽略密码错误或未完成四次握手的临时关联，避免周边旧设备/错误密码重连打断待机倒计时或误唤醒 `IDLE`。

### 3. 仓库文档与安卓端切换器

- `README.md`：重构项目首页说明，明确列出参考项目（`sprd-linux-devs/e5-linux`、`Enceka/linux-lts-e5`、`CharlesGool/e5-sleep-kernel`、`kanoqwq/openwrt-tools`）、本仓库主要改动、刷机与更新步骤、默认管理地址与账密（`root/root`）、双系统切换方式及文档阅读路线。
- 新增 `openwrt系统切换器安卓版.apk`：用于在原厂 Android 系统内切换回 OpenWrt（需 root 权限）。

### 4. 测试覆盖

- `devices/test_power_state.py`：新增未认证客户端过滤、板级默认值继承、DEEP 唤醒停留 `IDLE`、亮屏不拉基带、Wi-Fi/USB 连入立即唤醒联网等单测，全部通过。

## 历史记录（r20261123）

### 1. 修复畅行60 开机 90 秒锁网重放超时与 AT 通道分流遗漏

- `rootfs/overlay/opt/e5/e5-at`：补齐 `changxing60` 与 `y60` 到 `t551m-at`（`nr2/nr6/nr7` 独立 AT 通道）分流白名单（短信相关命令仍保持由 ModemManager 独占）。
- 解决了开机时 `ModemManager-wrapper` 等待 `boot-replay early`、而 `e5-at` 又回退等待 `ModemManager` 导致的 90 秒死锁超时，以及进入后台首次提示 `Lock state unavailable; refresh to read the modem` 的问题。
- 真机实测：`boot-replay early` 从 90 秒超时降至 0.81 秒完成，`ModemManager` 开机 3 秒启动，5G `wan` 约 15 秒拨通，锁网缓存 `/tmp/unisoc-modem/sim0/lock.json` 开机自动生成。

### 2. 修复单卡休眠唤醒后基带复位与循环掉网

- `openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/data-sim`：在向指定卡槽发送 `AT+SPACTCARD=<slot>;+SFUN=4/5` 之前，先执行只读探测 `AT+SPACTCARD=<slot>;+CPIN?`（与 ModemManager 冷启动补丁对齐）。若明确返回 `+CME ERROR: 10`（无卡），则跳过该空槽的 `SFUN` 操作，避免对空 SIM 槽启动协议栈触发展锐 CP 复位（`modem@2/modem@3` 重启及 `nr2` AT 通道进入 `quarantined`）。
- `openwrt/overlay/usr/libexec/e5-power-state`：`restore_radio()` 仅在全部待恢复卡槽均成功开启后才删除 `/etc/e5/power-radio-restore.json`；若部分失败，逐槽记录已完成进度并保留标记，每 15 秒自动重试未恢复的卡槽，成功后自动拉起 WAN。
- 真机实测：畅行60 单卡（SIM1 在位、SIM2 空槽）连续完成 4 次真实 DEEP 深度休眠与唤醒（`suspend_stats/success=4, fail=0`），每次唤醒后 5–7 秒自动恢复 5G 联网，无基带复位与 AT 隔离报错。

### 3. 修复 BusyBox 下 TTL 规则应用失败

- `openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/ttl-engine`：将 BusyBox `flock` 不支持的 `flock -w 10 -x 9` 改为兼容的 `flock -n -x 9` 重试循环，消除开机 `S97unisoc-ttl` 与 `ifup wan` 时的 `flock: unrecognized option: w` 及 `Failed to apply saved TTL` 报错。

### 4. 测试与已知边界

- 补充单元测试：`devices/t551m/test_at_routing.py`、`devices/test_power_state.py`、`openwrt/tests/sim-radio.py` 全部通过（60/60）。
- 已知现象：插着充电器进入 DEEP 时，展锐充电管理驱动的 `Charger Manager wakeup timer`（约 6 秒）会周期唤醒系统；纯电池待机未做整夜长睡耗时统计。

## 历史记录（r20261122）

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
