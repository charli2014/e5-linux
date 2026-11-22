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

## 2026-11-18 屏管线状态解析缺陷：ctl_exec 输出去换行

CI run 44322121153 编译全部通过，但 test_screen_native.py 的
ScreenPipeline 4 项失败：output-ctl 只被调 status，on/off 从不发出。

根因：screen-power.c 的 ctl_exec 读 output-ctl 输出后未去掉尾部换行，
而 e5-output-ctl status 用 puts("on"/"off") 带 \n。ctl_state() 以
strcmp(v,"on") 比较 "on\n" 永不等，恒返回 -1。真机后果：熄屏时
state==1 不成立，管线 off 命令不发（两段式息屏静默退化为仅关背光）；
唤醒时 ctl_state()==0 不成立，亮屏前不先恢复管线（可能点亮黑帧）。
同文件 uci_get 本有 strcspn 去换行，ctl_exec 漏了。

改动：screen-power.c ctl_exec 读到输出后补 out[strcspn(out,"\r\n")]=0。
该 C 测试此前本地无 gcc、WSL 损坏从未执行，本次 CI 首次运行即暴露。
验证以 CI Linux 为权威（changxing60-release.yml 屏组件测试步骤）。

## 2026-11-19 唤醒测试断言修正 + 锁屏在线设备数

CI run 44523481567：去换行修复生效，ScreenPipeline 15 项中 4 失败降为
1 失败。余下 test_wake_enables_pipeline_before_backlight 断言
calls()[0]=='on' 过严：reconcile 唤醒路径先 ctl_state() 查询（记为
status）再发 on，实际序列 ['status','on']。该断言在"先查后开"设计下
从未成立（修复前 on 不发亦失败）。功能语义无误——管线先于背光使能由
reconcile 代码顺序保证，末态 brightness=180、ctl_state=on 均成立。
改断言为精确序列 ['status','on']；其余唤醒测试用 assertIn 不受影响。

锁屏首页新增"在线设备 N台 · Wi-Fi x · USB y"（无设备时"无在线设备"，
圆点置灰）。数据复用状态接口现成 clients（hostapd get_clients + DHCP
租约，base/api.uc），后端零改动；mobile.js 锁屏渲染回调直接取
data.clients，mobile.css 复用 .lock-online 布局加 .empty 灰点。
mobile.js 经 stage.py 原样拷贝、mobile.css 仅字体缩放，不触锚点替换。

## 2026-11-19 block-mount 容器改原生架构（CI 第三次失败修复）

CI run 44537126234：编译与屏测试全过、缓存首次落盘（key …d20b54ce），
第 15 步 block-mount 失败。原因：block-mount.Dockerfile 用 ubuntu:22.04
且 --platform linux/amd64 硬编码，ARM runner 上整个容器（含 apt）跑在
qemu-x86_64 仿真下，jammy keyring 解析坏（NO_PUBKEY 871920D1991BC93C）。
修复对齐 hostapd/lpac 已验证模式：debian:trixie 基础镜像 + uname -m
判定 PLAT（ARM runner 原生 arm64 容器），x86_64 SDK 二进制经宿主
binfmt_misc 在容器内运行。补装 util-linux（flock）。改动不在编译缓存
key 的 hashFiles 范围内，下次运行编译步直接命中缓存（省约 57 分钟）。

## 2026-11-20 block-mount 二次修复：qemu 下 m4 段错误

CI run 44727593916：容器架构修复生效（apt/SDK 下载/feeds/约 35 分钟交叉
编译全过），但 fstools 的构建依赖 util-linux 在 ninja 180/701 步失败：
SDK 自带 x86_64 bison 调 m4 子进程，m4 在 qemu-user 下段错误
（QEMU internal SIGSEGV MAPERR addr=0x20，bison: m4 subprocess got
fatal signal 11）。修复：容器补装原生 bison/flex/m4，inner 脚本每次
运行把 staging_dir/host/bin/{bison,flex,m4} 覆盖为原生架构二进制
（幂等，兼容已缓存 SDK），其余工具链继续走 binfmt。
另核实：block-probe 真 APK 测试断言 /lib/libblkid-tiny.so 无需改——
openwrt-25.12 分支 fstools Makefile（PKG_SOURCE_VERSION 与 pin 一致）
Package/block-mount/install 仍装 libblkid-tiny.so 到 /lib；util-linux
只是 PKG_BUILD_DEPENDS。

## 2026-11-20 首次组装缺 UFS 身份助手（CI 第五次失败修复）

CI run 44734389519：block-mount 全过（m4 修复生效），首次进入组装步，
3 秒即失败：stage-ufs.py 找不到 out/changxing60/ufs-id.build.json。
原因：ufs-id 静态 arm64 助手在构建机是一次性注册的本地输入，CI 从未
编过。修复：workflow 组装前新增步骤 python3 tools/build-ufs-id.py
--cc aarch64-linux-gnu-gcc（runner 已装该交叉编译器；产物路径与
tools/build-layout.json 默认一致，回执 sha 与 tools/ufs-id.c 源码绑定）。
同批把组装链剩余外部依赖全部静态核查：5 个助手+bootctl 用 --cc 默认
aarch64-linux-gnu-gcc 现编；at-client/at-owner/sml-voltage 同默认；
aurora 4 包按 sha 钉死从 GitHub Release 下载（本次 run 已过该步）；
kernel 产物完整性由 check-container-support 在组装前通过自证；
installer 子模块递归检出（pin 57e159c）；audit 断言逐项对照属主源码。

## 2026-11-20 misc 种子来源错误 + F2FS 恢复 bundle 缺口（CI 第六次失败修复）

CI run 44740856762：ufs-id 步骤通过、干净 root 与全部 apk 安装通过，
组装在 boot/build-boot-image.py:148 失败：'Selected Android slot is
not successful/bootable'。
取证：解码提交的 ci-seeds/misc-head.bin，BC 为 suffix _a、
slot a=0x2f（优先级15/tries2/_successful=0_）、slot b=0x9e
（优先级14/tries1/successful=1）——与 bootloader_control() 对
"Android 在 b 槽、优先级15" 生成的 Linux 试用块逐字节一致。
即该种子取自刷过 Linux 的运行中设备（试用态），不是出厂 misc；
构建器按 suffix 推导出 Android 槽=a（Linux 试用槽，successful=0），
校验正确拒绝。本机 Android 实际在 b 槽。
修复：把种子重建为出厂 Android 回退态（suffix _b、slot b=0x9f
优先级15/tries1/successful、slot a=0，CRC 重算）。验证：由此生成的
Linux 试用块与设备当前_misc BC 逐字节相同_，Android 回退块
（b 槽 p15 successful）语义与 r20261114 一致；不削弱任何校验。
tools/tests/ci-seeds.py 16 项全过。
同批前置审计发现下一个必然缺口：boot 镜像需要 out/boot/f2fs-tools
早期恢复 bundle（fsck.f2fs/resize.f2fs 等 14 件），CI 从未生成；
钉死 clean base 只带 libf2fs6/mkf2fs，缺 f2fsck。修复：组装 apk
步骤补装 f2fs-tools（25.12.5 源内 1.16.0-r4，与 base 库同版；
f2fsck 提供 fsck.f2fs 及 resize.f2fs 符号链接，已对照 openwrt-25.12
Makefile 核实），并在 boot 构建前用 boot/prepare-f2fs-tools.py 从
组装好的 root 直接生成 bundle——不再依赖构建机一次性注册输入。
其余组装后段逐项核实无外部缺口：ext4-tools 只需 base 内
e2fsck/resize2fs/flock+readelf（binutils 已装）；GUI/Diff Studio
工件由 prepare-installers 按 installer-inputs.lock.json 下载并在
input_check 预校验（上次 run 已过该关）；switch-apk 回执在库内。

## 2026-11-20 组装首次成功；Collect 步 root 目录写权限（CI 第七次失败修复）

CI run 44750619884（7609b94）：**组装步首次全程通过**——misc 种子修复
生效（boot 镜像构建过）、f2fs-tools 补装+bundle 生成生效（日志
'Staged ARM64 fsck.f2fs bundle'）、干净 root 审计过、mke2fs/e2fsck 过、
ext4-tools/install-lock 过、finalize+安装包自检过，产出
changxing60-openwrt-25.12.5-r20261120.145034-g7609b941-se7d033a9-k6.18.54.zip
（272,856,695 字节），build-release 校验 state=complete。
失败移到下一步 Collect release files and notes（exit 1，无 ::error::
注解→不是显式错误分支）。定位：组装用 sudo 跑，out/releases/<task>
归 root 所有（755），Collect 以 runner 用户往其中写 SHA256SUMS
（shell 重定向）与 release-notes.md（python write_text）必然
Permission denied；latest.json state=complete 证明目录已完成改名、
find 能找到，排除"无 release 目录"分支。修复：Collect 开头
sudo chown -R runner out/releases。publish job 只读 artifact 不受影响。
tools/tests/ci-seeds.py 16 项过。

## 2026-11-21 出包成功、真机核查与 P0 升级配置迁移

CI run 44849582263（5d01638）全部通过，发布
changxing60-openwrt-25.12.5-r20261121.020000-g5d016382-s37758b6e-k6.18.54
（zip 272,771,265 字节）。用户当日用该包 --update 刷机并重启。

真机只读核查（root@192.168.9.1，取证脚本在 work/power-audit/，未入库）：
- 版本：内核 6.18.54-changxing60-bringup4，/etc/e5/image-version 与
  release commit 一致。
- 生效：workqueue.power_efficient=1、PM_DEBUG（/sys/power/pm_test）、
  e5-power S97/K05 + 状态机 ONLINE（idle30/deep0/hold5）、DEEP 门同时读
  wake_lock 与 wakeup_sources 且两者可读、cage+cog --scale=1.25、
  e5-output-ctl 实测 status=on、锁屏在线设备数（#lock-clients，按
  wifi/usb 分类）、aurora 主题、LuCI admin/modem/power（view mu300/power，
  ubus e5-power get 正常）、ttyd/msmtp/openssl、sipa_eth0 数据与 ping、
  e5-ufs-id + sml-voltage-check + media-max=33。
- 更新布局：misc 变为 suffix _b（Linux 试运行在 b 槽，Android 回退在
  a 槽 p14/successful），即更新写非活动槽；试用槽不标记 successful 与
  r20261114 长期运行状态一致，属既定设计。
- 开机 2 条 ModemManager "couldn't find the ModemManager process" 为启动
  竞态，MM 1.24 起来后 modem/bearer 正常连接，不处理。

发现真实升级缺陷（P0 未生效）：升级 keep_config（device-install-image.sh
拷贝旧 etc/config）把镜像内 stage.py 写入的 pipeline_off/pipeline_grace
覆盖掉；screen-power.c 缺该选项即退回"只关背光"。证据：设备
/etc/config/e5-infoscreen mtime 11-19（早于本包 11-21 构建时间），
uci get 两个选项均 Entry not found。全新刷机不受影响。
修复（用户选 C）：
1) 设备端已补 uci set pipeline_off=1 / pipeline_grace=10 并重启
   t551m-screen-power；实测息屏 13 秒后 e5-output-ctl status=off，
   点亮后恢复 on——管线关断真机首次验证通过。
2) 仓库加幂等迁移：stage_screen 额外写
   etc/uci-defaults/97-changxing60-screen，仅在选项缺失时补默认值
   （显式 0 保留用户选择）。新增 devices/changxing60/test_screen_defaults.py
   3 项（新鲜配置写入+幂等、显式选择保留、迁移脚本仅补缺失），
   并加入 CI 测试步。

## 2026-11-21 挂起补丁栈接入（DEEP 的硬阻断已解）

上文 DEEP 试验第 1 步的看门狗阻断已有代码方案：`devices/common/power/`
下 0001（UMP9620 看门狗跨挂起停/恢复）、0002（DPU wb_work 判空）、
0004（GPU 域挂起关断）、0005/0006（相机域 genpd 与厂商标时序）已由
`devices/changxing60/prepare-kernel.py` 接入畅行60内核准备，随 CI 新包
编译。五个补丁对供体 `Enceka/linux-lts-e5@020b970e` 已验证可干净应用。

状态区分：
- 已核实：补丁可应用、CI 会编译；E5 上相机+GPU 关断后 AP 能进 PMU 深睡。
- 未核实：畅行60 真机挂起存活、唤醒时延、电量收益、本机 DT 是否有相机
  域节点。`deep_min` 仍为 0；真机三步试验见
  `docs/SUSPEND-PATCHES-20261121.zh-CN.md`，通过前不改默认值。
- procd 的看门狗参数不变；变化在内核驱动：挂起时停狗、恢复时重新武装。

因此上文"第 1 步先看门狗、挂起会触发重启"的历史描述只适用于旧包；
新包请按新文档执行，仍须有人在场。

## 2026-11-22 USB3/dwc3 运行时挂起（仅畅行60）

真机只读核查：dwc3 在 gadget `not attached` 时仍 `power/control=on`，
active_time 1,257,855 ms、suspended 0；父 glue `25100000.usb3` 已是
`auto` 且 active。受控写入 UDC 自己的 `power/control=auto` 后进入
`suspended`，恢复 `on` 后累计 29,804 ms 挂起；父 glue 未动。

实现：

- `devices/changxing60/stage.py` 写 `/etc/e5/usb-autosuspend`（内容 `dwc3`），
  只在本机型镜像存在；其它机型不受影响。
- `e5-power-state` 的 `Ops.usb_runtime_pm()` 在启动时只遍历
  `sys/class/udc/*/power/control`，把 `on` 改 `auto`，不碰父 glue；
  UDC 不存在或标记缺失时静默跳过，失败只记日志。
- `devices/test_power_state.py` 增加 4 项：标记生效、其它板标记忽略、
  UDC 缺失不报错、无标记不写。

**未验证**：插数据线能否从 runtime suspend 唤醒并重新枚举，USB 串口
控制台是否受影响。若异常，删除 `/etc/e5/usb-autosuspend` 或把对应
`power/control` 写回 `on` 即可复现对照；Wi-Fi/LuCI/SSH 仍是管理通道。
估算收益 3–10 mA，未做整机 A/B。审计数据与禁区见
[省电审计](POWER-AUDIT-20261122.zh-CN.md)。
