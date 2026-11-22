# 畅行60 内核/驱动省电审计（2026-11-22）

机型：畅行60（ZTE 7552N / P720S20，UMS9620）。
前提：**5G SA 和高速 Wi-Fi 两条链路不降速、不改配置**。
目标：在 ONLINE 状态找出内核和驱动层还能省的电，并把已经确定的项写入代码。

本文的“实测”全部来自 2026-11-21/22 的真机只读取证和一次受控的 dwc3 运行时
挂起 A/B；采样脚本留在本地 `work/power-audit/`，含设备凭据，不入库。
电流采样噪声大，本文不拿单点电流宣称瓦数收益。

## 结论先行

1. **ONLINE 的主要功耗仍是 Wi-Fi AP + 5G SA 本身**。这两条按前提不动，
   其余内核/驱动项加起来的量级远小于它们；不要为了几十毫安去动射频。
2. **dwc3 控制器是已确定的浪费**：gadget `not attached` 时仍
   `power/control=on`，active 约 1258 秒、suspended 0 秒。写 `auto` 后
   立即进入 `suspended`；恢复 `on` 后 active，并累计约 29.8 秒挂起时间。
   本次已写进代码：仅畅行60 镜像在启动时把 UDC 自己的节点改为 `auto`，
   不改承载 5G 数据路径的父 glue。
3. **VBC/AGDSP 是第二处确定的活动域**：所有 PCM 已关闭后，
   `56510000.vbc` 仍 active 843 秒、suspended 4.5 秒，并让
   `agdsp-access` 电源域保持开启。代码层没有安全的“空闲即卸载/断电”路径，
   本次只记录，不做猜测性改动。
4. **UFS 已经是厂商省电参数，但仍不进入 runtime suspend**：
   `clkgate_enable=1`、10 ms、RPM/SPM level 3、`pm_qos_enable=1`，
   active 863 秒、suspended 0 秒。再改参数缺少本机可控验证，暂不动。
5. CPU idle 本身已经不错（cluster 电源域关闭占比 72–96%，本次窗口 83%），
   没有“关核/锁频”的必要；那会破坏 5G/Wi-Fi 吞吐。

## 实测窗口

60 秒采样（电流为 `current_now` 连续读数，负号代表放电）：

| 项 | 读数 |
|---|---|
| 电流样本 | -322 / -247 / -204 / -224 / -128 / -270 mA |
| 亮度 / blank / DSI | 0 / 4 / disabled |
| 系统睡眠能力 | `mem_sleep = s2idle [deep]` |
| 挂起统计 | 全部为 0（本次窗口没有真挂起） |
| cluster 电源域关闭 | 398,014,688 µs，约占 83% |
| 主频分布 | 1.105 / 1.2288 GHz 为主；CPU7 2.21 GHz 累计 858 tick |
| arch_timer | 约 152 次/秒 |
| timer@40000 | 约 132 次/秒，固定在 CPU0 |
| mmc2 | 约 6.3 次/秒 |
| mailbox / sipa / sdiohal / ufshcd | 4 / 2.5 / 2.3 / 1.7 次/秒 |
| softirq | RCU 120、SCHED 96、TIMER 58 次/秒 |
| WiFi RPS | rx-0 指向 CPU2 |

采样时屏幕已关闭、热点无客户端；设备仍在 ONLINE。**只要有一个热点客户端
关联，`e5-power-state` 就把设备视为有活动，不会进入 IDLE/DEEP**——这是既定
策略，不是漏电。夜间掉电要先确认当时是否有客户端或 USB 数据口。

CPU 拓扑：三簇 4×377 / 3×1022 / 1×1024 容量，`core_id` 在不同簇重复为
0/1/2；schedutil；MENU idle governor（TEO 关闭）；SCHED_MC 关闭；
PREEMPT_NONE；HZ=250；NO_HZ_IDLE。对这些参数做“省电优化”的收益远小于
破坏调度/吞吐的风险。

## 已确认的三处

### 1. dwc3：控制器常亮（已写入代码）

设备路径：
`/sys/devices/platform/soc/soc:ipa-apb/25100000.usb3/25100000.dwc3`。

| 项 | 值 |
|---|---|
| UDC 状态 | `not attached` |
| `power/control` | `on` |
| `active_time` | 1,257,855 ms |
| `suspended_time` | 0 ms |
| 父 glue `25100000.usb3` | `auto`，active（5G 数据路径的一部分，不能动） |
| 用户态写者 | 未发现 |

受控 A/B（只写 UDC 节点）：

1. `power/control=on` → active，持续采样均为 active。
2. 写 `auto` → `runtime_status=suspended`，所有采样一致。
3. 恢复 `on` → active，`suspended_time=29,804 ms`，说明挂起确实发生并被累计。
4. 父 glue 保持 `auto/active`，未观察到 5G 数据路径变化。

代码落点：

- `devices/changxing60/stage.py` 在镜像里写 `/etc/e5/usb-autosuspend`（`dwc3`）。
- `openwrt/overlay/usr/libexec/e5-power-state` 启动时只把
  `sys/class/udc/*/power/control` 从 `on` 改为 `auto`；其它机型没有标记文件，
  不做任何修改。
- 测试：`devices/test_power_state.py` 新增标记识别、只改 UDC、不碰 glue、
  缺失节点不报错四项。

**未验证**：插数据线能否从 runtime suspend 正常唤醒并重新枚举。设备仍有
Wi-Fi/LuCI/SSH；若串口控制台异常，删除标记或把节点写回 `on` 即可对照。
估算收益 3–10 mA，未做整机 A/B，不作为发布承诺。

### 2. VBC/AGDSP：开机音频后一直在线（仅记录）

| 项 | 值 |
|---|---|
| 节点 | `56510000.vbc` |
| 运行时间 | active 843 s，suspended 4.5 s |
| PCM | 全部 closed |
| 关联电源域 | `agdsp-access` 保持开启 |

这说明“没有播放”不等于 VBC/AGDSP 已断电。可行的方向是让 VBC 驱动在
所有 PCM 关闭且无通话时进入 autosuspend，或由音频属主在不使用时卸载模块；
但本机音频链路（hostless 通话、PA 路由、DSP 固件）耦合多，缺少安全的
恢复验证，本次不改。估算 2–8 mA，需单独做“播放/通话/空闲”三态 A/B。

### 3. UFS：厂商省电参数已开，但从不 runtime suspend（仅记录）

| 项 | 值 |
|---|---|
| `power/control` | `auto` |
| 运行时间 | active 863 s，suspended 0 s |
| `clkgate_enable` | 1 |
| `clkgate_delay_ms` | 10 |
| `rpm_lvl` / `spm_lvl` | 3 / 3 |
| `pm_qos_enable` | 1 |
| `wb_on` | 1 |

这些正是厂商的省电配置，但控制器在空闲时仍未挂起。可能原因包括上层
持续访问、QoS 请求或驱动未允许 runtime PM；没有本机可复现的对照前，
不通过改 sysfs 或补丁“强行挂起”。估算 5–20 mA，风险是存储 I/O 卡顿和
更新失败，优先级低于 dwc3。

## 可行清单（按证据强度排序）

| 项 | 预估 | 状态 | 说明 |
|---|---|---|---|
| dwc3 runtime suspend | 3–10 mA | **本次已实现** | 仅畅行60；插线唤醒待复核 |
| VBC/AGDSP 空闲断电 | 2–8 mA | 仅记录 | 需要安全卸载/恢复路径 |
| UFS runtime suspend | 5–20 mA | 仅记录 | 厂商参数已开但不挂起；需驱动级定位 |
| SIM/网络轮询绑定小核 | 1–5 mA | 仅评估 | 当前轮询分散；改绑可能影响时延 |
| TEO idle governor | <1–2% | 仅评估 | MENU 已工作；TEO 收益小，需 A/B |
| 关闭串口控制台 | 1–3 mA | 不建议默认做 | 失去断网恢复通道 |

## 不建议做

- **改 5G SA 或 Wi-Fi 配置**：前提明确禁止；这两项是 ONLINE 功耗主体。
- **锁 CPU 频率/关核/改调度器**：当前 cluster 电源域关闭占比已高，
  强行限制会直接伤吞吐与时延。
- **长时间强制 suspend**：热点有客户端时设备必须在线；DEEP 仍待受控试验。
- **读取 `clk_summary` 或裸遍历时钟 regmap**：本机会 SError panic，见附录。
- **移除 `clk_ignore_unused` / `pd_ignore_unused` / `regulator_ignore_unused`**：
  本机 cmdline 从来没有这三个参数，这是其它机型的历史表述，不适用。
- **用单点电流判断收益**：`current_now` 波动可达 ±100 mA，必须做同条件
  A/B 或看 `suspended_time` 这类确定性计数。

## 建议的验证顺序

1. 先复测 dwc3：无数据线时看 `power/control=auto`、`runtime_status=suspended`、
   `suspended_time` 增长；插数据线看是否唤醒并重新枚举；串口控制台是否可用。
2. 有客户端/无客户端各做一次 10 分钟同条件电流采样，确认 IDLE 判定符合预期。
3. VBC：播放结束、通话结束、纯空闲三态下读 `runtime_status` 与
   `agdsp-access` 状态，再决定是否做驱动改动。
4. UFS：只在只读空闲场景观察；任何更新/安装测试前先恢复默认。
5. 深睡：按 `SUSPEND-PATCHES-20261121.zh-CN.md` 的三步受控试验执行，
   通过前保持 `deep_min=0`。

## 附录 A：`clk_summary` 导致内核 panic

2026-11-21 真机取证时执行：

```sh
cat /sys/kernel/debug/clk/clk_summary
```

约 7312 秒时内核打印：

```text
SError Interrupt on CPU6
...
regmap_mmio_read32le
sprd_gate_is_enabled
clk_core_is_enabled
clk_summary_show_subtree
...
Kernel panic - not syncing: Asynchronous SError Interrupt
```

触发进程为 PID 12034 `head`。设备随后重启，网络恢复后重新连上。
这不是 UFS I/O 故障，也不是省电改动的回归；根因是跨电源域读取时钟门控
寄存器。**不要再用该节点做功耗对比**。需要时钟状态时，用 DT、驱动源码、
构建产物和 `debugfs` 之外的有界接口交叉核对。

## 附录 B：为什么夜里掉电不一定是“漏电”

`e5-power-state` 的活动判定包含：

- hostapd 关联客户端数；
- USB 数据口（UDC `configured` 或 `usb0` carrier；纯充电器不算）；
- 背光是否大于 0。

任意一项为真就保持 ONLINE。热点客户端连着时，设备会一直开热点和 5G，
不会进入 IDLE/DEEP。夜间掉电应先看 `/run/e5-power.json` 的 `state`、
`deep_blocked`、`last_error`，再看是否有客户端或 USB 数据口，而不是先改
内核省电参数。

## 相关文档

- [待机状态机与界面](POWER-STANDBY-20261117.zh-CN.md)
- [系统挂起补丁栈与受控试验](SUSPEND-PATCHES-20261121.zh-CN.md)
- [本机 CPU/调压依据](../devices/changxing60/CPU-POWER.zh-CN.md)
- [本机逐轮适配与未验收项](../devices/changxing60/README.md)
