# 畅行60 系统挂起补丁栈（2026-11-21）

机型：畅行60（P720S20，UMS9620）。本文说明 `devices/common/power/` 下五个
挂起补丁的内容、接线方式和真机受控试验步骤。默认 `deep_min=0`（深睡禁用）
不变；试验通过后再由用户调大。

## 结论先行

- 六个补丁已接入畅行60内核准备流程（`devices/changxing60/prepare-kernel.py`），
  CI 内核 job 会真实编译它们。
- 已核实：补丁顺序为 0001→0002→0004→0005→0006→0007，对登记的供体内核
  `Enceka/linux-lts-e5@020b970e` 都能干净应用；0006 是 0004/0005 的增量，
  0007 是 0006 的增量。
- 已核实（仅 E5 实测）：相机域和 GPU 域在挂起时关断后，AP 才能进 PMU
  深睡（`AP_DEEP_SLEEP_CNT` 0→1→2）。
- 已核实（畅行60 只读测量，2026-11-26）：本机 DT 的相机节点是
  `sprd,qogirn6pro-camsys-domain`，九个寄存器三元组和 `clk_mm_eb` 齐全；
  而未加 0007 时该驱动不绑定，PD_CAMERA 一直报告为开（DBG_6=0），
  两次真实挂起（20 s、44 s）里 AP/PUB 深睡计数都没有增加。0007 就是补这一条。
- 未核实：0007 刷机后计数是否前进、畅行60 真机挂起存活、唤醒时延、电量收益。
- 不做：不改射频/热点策略、不改轮询、不主动发起挂起、不动 eMMC。

## 为什么需要这组补丁

畅行60 的 DEEP 状态机（`openwrt/overlay/usr/libexec/e5-power-state`）写
`mem` 进入系统挂起，但当前内核有两个硬阻断：

1. **看门狗复位**：procd 打开 `/dev/watchdog`，由 `ump9620-wdt` 驱动喂
   UMP9620 PMIC 看门狗，超时 30 秒。PMIC 在挂起期间不断电、用户态已冻结，
   没有补丁时任何超过 30 秒的挂起都会被复位。这是一次“安全失败”，但会让
   真睡试验永远无法完成。
2. **子系统不关断**：PD_CAMERA 与 PD_GPU 都是没有自动关断的独立 PMU 域，
   相机域开机就带电、GPU 只在驱动卸载时才关。两者亮着时 AP 进不了 PMU
   深睡（`AP_DEEP_SLEEP_CNT`、`PUB_DEEP_SLEEP_CNT` 恒为 0）。

## 补丁清单

| 补丁 | 目标 | 作用 | 缺失后果 |
| --- | --- | --- | --- |
| 0001 | `ump9620-pmic-wdt.c` | 挂起前停狗、恢复时按完整超时重新武装，与 Android PM 固件一致 | 挂起 >30 s 被看门狗复位 |
| 0002 | `sprd_dpu.c` | `wb_work` 未初始化时不调用 `cancel_work_sync()` | 每次挂起刷一条内核警告 |
| 0004 | `panfrost_sprd.c` 等 4 个文件 | 挂起路径关 GPU 核时钟门、强制 PD_GPU 关、DCDC 下电、释放 GPLL；恢复时重放上电序列，并把 `GPU_PM_CLK_DIS` 打开 | PD_GPU/GPLL 常亮，AP 进不了深睡 |
| 0005 | `sprd_camsys_pd.c`（新增） | 把 DT 的 `sprd,qogirl6l-camsys-domain` 注册成 genpd，开机即关相机域 | 相机域常亮，AP 进不了深睡 |
| 0006 | `sprd_camsys_pd.c`、`panfrost_sprd.c`、Kconfig | 按 E5 原厂 qogirn6l 时序重写 DCAM/ISP/TOP 三档关断（force/automatic/state、300–350 µs、连续三次读一致、最多 30 次）；GPU 上电任一步失败整体回滚；相机提供者改为内建 | 关断时序与厂商不一致，失败路径半上电 |
| 0007 | `sprd_camsys_pd.c` | 让相机提供者也匹配畅行60 的节点名 `sprd,qogirn6pro-camsys-domain` | 驱动不绑定，相机域常亮，AP 进不了深睡 |

细节与逐行说明见 `devices/common/power/README.md`。

## 接线方式

`devices/changxing60/prepare-kernel.py` 在各板级准备脚本之后调用
`apply_power_patches()`：

- 补丁按固定顺序从 `devices/common/power/` 读入，CRLF 归一化后通过
  `git apply -` 应用，Windows 工作区和 Linux CI 行为一致。
- 幂等：若 0007 已能反向应用，说明整套已打上，直接返回；被复用的本机
  内核视图不会重复打补丁。
- 任一步失败立即 `SystemExit` 并打印 `git apply` 的 stderr，不会带着半套
  补丁继续编译。
- 只对畅行60生效；41S/M8/E5 的准备工作不调用它。

脚本内固定清单（顺序即应用顺序）：

```
0001-watchdog-ump9620-stop-across-system-suspend.patch
0002-sprd-dpu-no-cancel-of-uninitialised-wb-work.patch
0004-drm-panfrost-sprd-power-the-GPU-off-across-system-su.patch
0005-soc-sprd-add-the-UMS9621-camera-subsystem-power-doma.patch
0006-sprd-stock-power-sequence-and-error-unwind.patch
0007-soc-sprd-bind-the-UMS9620-camera-power-domain.patch
```

## 配置前提

- 基线 `devices/changxing60/ci-seeds/ums9620-base.config` 已含
  `CONFIG_SPRD_CAMSYS_PD=y`；构建在打完补丁后执行 `olddefconfig`，符号因此
  被保留而不是当作未知项丢弃。
- 依赖项同样已在该基线中：`CONFIG_PM_SLEEP=y`、
  `CONFIG_PM_GENERIC_DOMAINS_OF=y`、`CONFIG_UMP9620_PMIC_WATCHDOG=y`、
  `CONFIG_DRM_PANFROST=m`。
- `devices/changxing60/kernel.config` 保留 `CONFIG_PM_DEBUG=y`，提供
  `/sys/power/pm_test` 供第二步 staged 试验。

## 构建与验证

CI 入口不变：`.github/workflows/changxing60-release.yml`，内核 job 调用
`devices/changxing60/build-kernel.py`，再由它执行 `prepare-kernel.py`。
一次完整出包约 1.5 小时（内核 ~20 分钟，安装包 ~57 分钟）。

构建完成后的人工核对：

1. 内核交付里的 `config` 含 `CONFIG_SPRD_CAMSYS_PD=y`。
2. `modules.builtin` 含 `drivers/soc/sprd/domain/sprd_camsys_pd.o`。
3. 设备启动后 `dmesg | grep -i camsys` 出现
   `camera/DCAM/ISP domains off; power managed by genpd`；若 DT 没有对应
   节点，则没有这行，且相机域保持原状——这本身不是故障。

## 真机受控试验（须有人在场）

先决条件：已刷入含本补丁栈的新包，`/etc/e5-power.json` 仍是 `deep_min=0`。

### 第一步：确认看门狗归我们管

- `ubus call system watchdog` 应显示运行中、约 30 s 超时。
- `dmesg | grep -i ump9620` 确认 `ump9620-wdt` 绑定。
- 补丁生效后，系统挂起时该驱动会停止 PMIC 看门狗；没有别的看门狗
  （`CONFIG_SPRD_WATCHDOG` 未开）。

### 第二步：pm_test staged 挂起

编辑 `/etc/e5-power.json`：`"deep_test": true`、`idle_min: 1`、
`deep_min: 1`。`logread -f | grep e5-power` 观察，并同时开
`dmesg -w`。

- 预期：`PM: suspend entry (deep)` → 数秒后 `PM: suspend exit`，不重启，
  无 `=== watchdog` 类复位标志。
- 失败时：`pm_test` 会被状态机复位，`deep_min` 改回 0，保留
  `logread`、`dmesg`、`/sys/power/state`、`/sys/power/wake_lock` 供排查。

### 第三步：真睡

去掉 `deep_test`，保持 `idle_min=1`、`deep_min=1`。

- 熄屏、拔掉 USB 数据线，等待进入 DEEP 后写 `mem`。
- 用电源键唤醒；记录从唤醒到 SSH/网络恢复的时间、是否异常重启、
  射频策略是否还原（`/etc/e5/power-radio-restore.json`）。
- 判定标准：不重启、能唤醒、网络恢复、无内核 Oops/Serror。
- 电量收益不在这一步下结论；需要单独的 A/B 采样（熄屏电流、挂起占空比）。

失败即回滚：`deep_min` 改回 0 即恢复现状（无需重刷）；把
`last_error`、`logread`、`dmesg` 留在设备上再分析。

## 已知边界

- 相机提供者匹配 `sprd,qogirl6l-camsys-domain` 和
  `sprd,qogirn6pro-camsys-domain` 两个节点名。畅行60 的节点已确认是后者，
  九个寄存器三元组与 `clk_mm_eb` 均存在；0007 只加这一条匹配，不改时序。
- DT 里另有几个 `power-domains = <&mm_domain>` 的消费者（dcam、isp、cpp、
  vdsp 等）。本机镜像没有这些相机驱动，理论上不会把它们拉起来；刷机后仍需
  用 DBG_6/DBG_7 读数确认相机域在开机和挂起后保持关闭。
- E5 的 `AP_DEEP_SLEEP_CNT`（PMU APB `0xdfc`）读法未移植到畅行60；
  本机第一步只以“挂起不重启 + 唤醒正常”为判据，计数器读数需要另行接
  只读调试通道。
- 0004 打开 `GPU_PM_CLK_DIS` 只影响 sprd Mali 数据；其它平台的 panfrost
  路径不变。
- 供体内核是公开的 `Enceka/linux-lts-e5`；补丁来源是
  CharlesGool/e5-sleep-kernel（GPL-2.0）。换供体提交后必须重新验证应用，
  构建入口会自动失败而不是静默跳过。

## 相关文档

- 待机策略与 IDLE/DEEP 状态机：`docs/POWER-STANDBY-20261117.zh-CN.md`
- 补丁逐条说明：`devices/common/power/README.md`
- CI 流程：`docs/CI-CHANGXING60.zh-CN.md`
