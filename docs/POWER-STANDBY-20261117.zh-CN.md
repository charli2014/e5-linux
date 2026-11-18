# 畅行60 省电待机（2026-11-17）

机型：畅行60（P720S20，UMS9620）。硬前提：ONLINE 状态网速不受影响。
本次范围：真关显示管线、IDLE/DEEP 分级待机、配套界面与更新保留。
前序屏幕定时器优化见 POWER-SAVING-20261024.zh-CN.md。

## 改动清单

### A0 Wi-Fi 恢复 uevent 修复
devices/wifi-common.py：uevent 改用 priv->wiphy->dev.kobj 并处理缓存树迁移，
修复一行缺陷；devices/test_wifi_recovery.py 用 wiphy/parent 语义桩验证。

### P0 两段式息屏，真关显示管线
cage 0.2.0 原生实现 zwlr-output-management-unstable-v1（output.c
handle_output_manager_apply → wlr_output_commit_state），不需要给 cage 打补丁，
也不动 feed 和共享构建链。

- 新增 devices/common/infoscreen/native/output-ctl.c：静态、零依赖的原始
  Wayland 线协议客户端（e5-output-ctl on|off|status）。off 对每个 head 下
  disable 并 apply；on 用 preferred/current mode 恢复并 apply。3 秒超时，
  协议错误退出 1，IO/超时退出 2。
- screen-power.c 改两段：息屏先写背光 0，grace（默认 10 秒，uci
  e5-infoscreen.main.pipeline_grace）后调 e5-output-ctl off 关整条管线；
  任何亮屏路径先恢复管线再写背光。off 失败按整段 grace 退避，不忙等。
  启动时若已全黑则直接 armed，避免首个 poll(-1) 永久阻塞。
- devices/changxing60/stage.py 幂等写入 pipeline_off '1' / pipeline_grace '10'；
  用户手动关掉的选择不被更新覆盖。其它机型不写，行为不变。
- build-screen-native.py 注册 e5-output-ctl，与 screen-power 一样静态链接。
- 测试：devices/t551m/test_output_ctl.py（10 项，AF_UNIX 假合成器，覆盖
  preferred mode 恢复、apply 失败、超时、socket 缺失）；test_screen_native.py
  新增 ScreenPipeline 7 项（先管线后背光、grace 不被提前 poll 缩短、gate
  关闭只控背光、客户端缺失降级、未知状态静默放弃）。

### P1 时钟与轮询
- native.h monotime() 改 CLOCK_BOOTTIME：sim-status/voice 的截止与节奏
  跨系统挂起不再被拉长。逐一核对过消费点，均为间隔/截止语义。
- atd.c、at-client.c、e5-noirq-play、unisoc-ra-renew、e5-sim-probe.c 的
  MONOTONIC 点复查过，无危害证据，不改。轮询削减由 IDLE 停服务实现。

### P3 内核配置
devices/changxing60/kernel.config：cmdline 追加 workqueue.power_efficient=1；
CONFIG_PM_DEBUG=y（为 DEEP 排查提供 /sys/power/pm_test 等接口）。

### IDLE/DEEP 状态机
新增 openwrt/overlay/usr/libexec/e5-power-state（python3）与
etc/init.d/e5-power（S97 启动，K05 停止——先于 modem 属主恢复射频）。

- 策略 /etc/e5-power.json：idle_min / deep_min / hold_awake_min / inhibit。
  畅行60 出厂 idle_min=30、deep_min=0、hold_awake_min=5。
  **deep_min 出厂 0（深睡禁用）**：真机挂起尚未受控验证，先只跑 IDLE；
  验证通过后在界面里调大即可，无需重刷。其它机型默认 idle_min=0，守护进程空转。
- 5 秒一拍。活动判定：hostapd get_clients 关联数、USB 数据口（udc
  configured 或 usb0 carrier，纯充电器不算）、背光 >0。任一读取失败按
  “有活动”处理，宁可不清睡也不漏唤醒。
- IDLE：经 unisoc-modem/data-sim 异步 job 逐卡关射频（SFUN=5 属主，
  不直接发 AT），停 e5-bt、t551m-sim-status；热点保持。关射频前把策略
  存到 /etc/e5/power-radio-restore.json——data-sim 会持久化策略，没有
  这个标记，IDLE 期间重启会以射频关闭状态开机。开机和唤醒都恢复。
- 唤醒：WiFi 关联、亮屏（电源键）、USB 数据口；恢复射频与服务后交
  /usr/libexec/e5-network-recovery 拉 WAN（不自己动 AT/射频）。
  唤醒后 hold_awake_min 保持清醒；IDLE 不足 120 秒被唤醒视为短待机，
  下次计时 ×2，封顶 ×4，完整待机后复位。
- IDLE 期间读到任一射频为开立即唤醒，不与人打架。data-sim 会持久化
  关断策略，IDLE 的正常读回是全关；不能拿入睡前的策略做比较，否则会
  把自己的关断当成用户改动而反复唤醒（测试覆盖此回归）。
- DEEP：/sbin/wifi down 后写 mem 挂起。前置门：pactl sink RUNNING、
  /sys/power/wake_lock 含 sipa、升级锁（e5-upgrade/lock、
  e5-part-update.lock）、USB 数据口。被挡则 5 分钟后重试并记录原因。
  挂起失败或唤醒后：wifi up、恢复射频/服务、WAN 恢复，回 ONLINE。
  deep_test=true 时经 /sys/power/pm_test core  staging（失败也复位
  pm_test），供受控测试，界面不暴露此开关。
- 状态写 /run/e5-power.json（state/idle_in/deep_in/hold_in/last_error/
  deep_blocked）；配置按 mtime 热加载，改计时不用重启。
- 升级锁被占或 inhibit：立即唤醒。SIGTERM（procd 停止/关机）先恢复再退出；
  被强杀也有开机标记兜底。

### 界面（LuCI 与屏幕共用一个后端）
- rpcd e5-power → unisoc-modem/power-control：get/apply/reset，原子写
  /etc/e5-power.json（0600，fsync 文件与目录），校验 0..1440 分钟。
- LuCI admin/modem/power（mu300/power.js）：状态徽章、倒计时、
  “深睡已禁用”“深睡暂缓：原因”、三个计时项与保持唤醒开关。
- 屏幕插件 devices/common/infoscreen/power/（manifest/backend.uc/前端），
  走同一个 ubus 对象，共享 staging 循环携带，六种 profile 都带。
- 升级保留：keep.d/e5-power；device-stage-part-update.sh、
  device-install-image.sh、device-install-part.sh 的 settings 列表加
  /etc/e5-power.json；集成屏幕应用列表 phone esim → phone esim power
  （part-update.sh 与两个 install 脚本共 6 处），旧更新器不会用旧插件
  代码盖掉新镜像。

## 验证状态（实事求是）

已通过：

- devices/test_power_state.py：28 项状态机测试（假属主 + 手动时钟，
  不碰真射频/服务/挂起），含 pm_test staging 3 项。WSL python3 运行。
- 回归：openwrt/tests/image-keep-config.py、update-device-files.py、
  devices/test_staging.py、devices/t551m/test_cpu_idle.py 通过。
- 全部新增/改动 Python py_compile、shell bash -n、JS node --check、
  JSON 解析通过。data-sim radio 请求字段（slot/current 字符串、enabled
  布尔、confirm）与 status 轮询接口已对照属主源码核实。

未运行（环境缺件，不是代码结论）：

- test_screen_native.py、test_output_ctl.py：需要 C 编译器。本机 WSL
  无 gcc，sudo 需密码；在注册构建机或 `sudo apt-get install gcc libc6-dev`
  后运行。test_wifi_recovery.py 同样需要 gcc，且要传入 vendor 内核树
  路径（本机 kernel/ 下无 sprd_wlan_combo 源码）。
- boot/tests/part-update.py：需要 busybox（WSL 未装）。
- 未部署真机：无整机功耗 A/B、无真实挂起/唤醒、无 LuCI/屏幕界面实机点验。
  此前测得的 ≈-288mA（≈1.08W）是上一轮单项对照，不是本次整方案的结论。

## DEEP 真机受控测试步骤（须有人在场）

1. 先看门狗：`ubus call system watchdog`。若硬件看门狗在挂起期间无法
   暂停，挂起会触发重启——这是安全失败，但必须先知道。本次不改 procd
   的看门狗设置。
2. 编辑 /etc/e5-power.json：加 `"deep_test": true`，临时 idle_min=1、
   deep_min=1。`logread -f | grep e5-power` 观察。pm_test core 会 staging
   挂起流程数秒后自动恢复，不真睡。
3. staging 通过后去掉 deep_test，deep_min 设回 0 以外想要的值，做真睡：
   电源键/USB 唤醒，记录网络恢复时间、有无异常重启、射频策略是否还原。
4. 任何一步异常：deep_min 改回 0，保留 last_error 与 logread 供排查。

## 编译与刷入

- 本机不能编译：无 /home/kano/openwrt-build 工作区、无
  dumps/changxing60-stock、installer 子模块为空。
- GitHub CI（release.yml）目前只构建 E5 主线：bootstrap inputs 与组装
  job 都不含 changxing60。走 CI 需补 vendor 内核、UMS9620 基线 config、
  原厂 boot/misc 模板和 profile 组装 job，本次未改 CI。
- 注册构建机：`sudo python3 tools/build-release.py package
  --workspace /home/kano/openwrt-build --profiles changxing60`。
- 刷入：PC 安装包菜单 6（--update），USB 网口 SSH 192.168.9.x；保留
  /etc/config、密码、SSH 密钥、流量记录、用户屏幕应用、NV、音频 XML、
  触控固件；不动 Android userdata/GPT。畅行60 的正式 update 尚未在硬件
  上验证过，第一次更新须有人在场。旧 ZIP 不含本次修改，必须重新打包。

## 遗留

- dpu_r6p0.c disable_vsync() 注释问题仍按旧台账保留：该 VSYNC 中断同时
  参与 writeback/CABC，P0 走合成器 atomic disable，不碰这个中断。
- 在线 sysfs 项（UFS host 从不挂起、dwc3 时钟未门控、wq 只读、
  AT+CLAC 不支持）已排除，无收益证据，不做。
- 未移除 clk_ignore_unused / pd_ignore_unused / regulator_ignore_unused。
## 2026-11-18 DEEP 门修复：SIPA 内核唤醒锁此前不可见

缺陷（真机只读核查确认）：wakelocks() 只读 /sys/power/wake_lock，那里只有
用户态锁。SIPA 的锁是内核 wakeup source，只出现在
/sys/kernel/debug/wakeup_sources。真机 wake_lock 为空，而
soc:ipa-apb:sipa-dele 的 active_since 非零（持锁约占运行时间 93%），
旧门会误判"无 SIPA 锁"而放行 DEEP。

改动：
- openwrt/overlay/usr/libexec/e5-power-state：wakelocks() 合并 wake_lock
  与 wakeup_sources 中活动条目（第 6 列 active_since 非零即持锁）；
  任一接口不可读时返回 unknown，enter_deep 对 unknown 阻塞
  （wakelock state unreadable），fail-closed，不猜。
- devices/test_power_state.py：新增 6 项（内核锁可见、已释放不列、
  用户态锁保留、两向不可读 fail-closed、门阻塞 unknown），共 34 项。

验证：真机 Linux python3 全 34 项通过（/tmp 临时目录运行后即删）。
Windows 本地跑会因 NTFS mtime 分辨率使 reload 漏读配置变更而随机失败，
与本改动无关；CI Linux 跑同一测试为权威（changxing60-release.yml）。
真机取证证据在工作区 work/power-audit/（不上传）。

澄清：上文"未移除 clk_ignore_unused / pd_ignore_unused /
regulator_ignore_unused"是 M8/T551M 时期历史表述。畅行60 真机
/proc/cmdline 从来没有这三个参数，test_profile.py 也禁止加入，
"逐个移除"试验不适用于本机。
