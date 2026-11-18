# 畅行60 GitHub Actions 编译与发布

工作流：`.github/workflows/changxing60-release.yml`。与 E5 的 `release.yml`
完全独立，互不影响；E5 发布流程不做任何改动。

## 流水线结构

| job | 运行器 | 内容 |
|---|---|---|
| `kernel` | ubuntu-24.04-arm | 公开内核源码 `Enceka/linux-lts-e5`（默认提交 `020b970e`，即本机登记的 UMS9620 供体基线）+ 仓库内种子基线 config，跑 `devices/changxing60/build-kernel.py`（含 prepare-kernel 补丁与全部板级测试），产出内核交付 tar |
| `build` | ubuntu-24.04-arm | 还原种子与锁定 clean base → `prepare-installers` 下载版本锁定的三平台安装器（sha256 + 源码指纹双校验）→ 导入 OpenWrt 25.12.5 armsr 基础镜像 → 省电/更新保留测试 → 编译 ModemManager/BlueZ/wifi-sae/iwinfo/lpac/原生屏组件（带缓存）与 guarded block-mount → `ci-inputs.py create` 引导门槛自检 → `sudo tools/build-release.py package --profiles changxing60`（唯一发布入口，Android 安装器由 input_check 自动构建）→ 校验 zip、写 SHA256SUMS 与发布说明 |
| `publish` | ubuntu-24.04 | 沿用 E5 的草稿 Release 流程：校验哈希 → 建草稿 → 上传 → 发布；已发布的 tag 拒绝覆盖 |

安装器不在 CI 从源码编译，而是走 `tools/installer-inputs.lock.json` 锁定的
上游已发布构件（`prepare-installers`，LOCAL-BUILD 的标准流程）。原因：
installer 子模块的测试套件在 GitHub 托管运行器上有平台缺陷（Windows
cp1252 编码/反斜杠路径语义，macOS 无 `os.listxattr`、/var 别名解析），
子模块仓库不在本 fork 名下、无法推送修复；锁定下载同样经过哈希与源码
指纹校验，不削弱验证。E5 的 `release.yml` 仍走源码编译，不受影响。

内核源码是公开仓库，**不需要公开任何厂商源码**。流水线自足：不需要
仓库 Variables、不需要设备 SSH、不需要外部构建机，全部输入来自仓库
本身与本 fork 的一个锁定 Release 资产。

## 输入来源（自足设计）

CI 需要而干净 checkout 没有的输入分三类：

1. **小件种子**（提交在 `devices/changxing60/ci-seeds/`，由
   `tools/ci-seeds.py` 还原并自检）：
   - `boot_a.template.gz`、`misc-head.bin`：只保留 Android 头/vbmeta/footer
     与 bootloader_control 的模板（剥离原厂内核与其余内容）；
   - `ums9620-base.config`：UMS9620 基线 config（校验两个登记标记）；
   - `busybox`：静态 ARM64 busybox（校验 ELF 机器号 183）。
   均取自 r20261114 已发布安装包，不含厂商固件、原厂内核或设备凭据。
2. **clean base 与出厂默认配置**（太大不进 git）：从 r20261114 安装包的
   `openwrt.ext4.gz` 提取根文件系统，剔除 `etc/config`、`etc/e5`、
   `lib/modules`、`opt/e5/android`、`lib/firmware/wcnmodem.bin` 与全部
   身份/凭据路径后打成 `base-e5.tar.gz`；20 个出厂默认配置单独打成
   `clean-openwrt-base.tar`。两者合装为 `cx60-ci-base.tar.gz`，以 4 个
   ≤40MB 分片上传到本 fork 的 `ci-inputs-25.12.5` Release（长上传在部分
   网络会被重置，分片更稳）。`tools/ci-base.lock.json` 锁定下载地址、
   整包与每个分片的 SHA-256；`tools/ci-seeds.py` 下载、逐片校验、拼接、
   再校验整包后才解包。base 必须含 `sbin/sysupgrade.openwrt`，不得含
   设备专属内容（`ci-inputs.py create` 门槛复检）。
3. **补丁 APK**（wifi-sae / iwinfo-ap-scan / lpac / ModemManager / BlueZ /
   block-mount / 原生屏组件）：全部由 CI 用仓库内脚本现编，带源码指纹
   缓存；不再随引导包分发，源码改动后自动重编，不会过期。

组装前跑 `tools/ci-inputs.py create --profile changxing60` 作为门槛：
对全部输入逐项 inspect 并打出引导包 SHA-256（写入发布说明）。门槛拒绝
base 里的设备载荷；门槛通过后补建空目录 `base/e5/opt/e5/android`
（prepare-root 要求该挂载点存在且为空）。

更换 base 版本时：重新提取、打包、分片上传到新 Release，更新
`tools/ci-base.lock.json` 的 url 与哈希即可；种子与 APK 无需改动。

## 触发方式

- 手动：Actions → "Build and publish Changxing 60 OpenWrt" → Run workflow。
  可选 `kernel_ref`（默认登记提交）、`publish`（默认开）、`prerelease`（默认开）。
- 打 tag：`git tag changxing60-v<日期> && git push origin changxing60-v<日期>`，
  自动构建并发布，tag 即 Release 名。

手动触发时 Release tag 取 zip 文件名（含私有版本号
`r<时间>-g<提交>-s<指纹>`）；同一 tag 已发布会拒绝覆盖，需换新 tag。

## 产物与定位

Release 资产：`changxing60-*.zip`（安装包，含 Windows/macOS/Android 安装器）、
`SHA256SUMS`、`BUILD-RUN.json`（源码提交、指纹、资产哈希）、`release-notes.md`。

畅行60 仍是 bring-up profile（`installation_hardware_verified: false`）：
发布说明固定带"正式刷机/更新未经硬件验证"提示，默认 prerelease。
包内省电待机为 IDLE 30 分钟、DEEP 出厂禁用（`deep_min=0`），
与台账 `docs/POWER-STANDBY-20261117.zh-CN.md` 一致。

## 已知约束

1. **种子与 base 锁按基线固定。** 补丁 APK 由 CI 现编，源码改动自动重编，
   不会过期；但基线 config、boot/misc 模板、busybox 与 clean base 更换时，
   需更新 `devices/changxing60/ci-seeds/` 或 `tools/ci-base.lock.json`
   （重新上传分片资产），否则门槛会拒绝不匹配的输入。
2. **安装器锁。** `installer` 子模块提交必须与
   `tools/installer-inputs.lock.json` 一致（与 E5 发布同一把锁）；
   `prepare-installers` 按锁下载并校验三平台构件，子模块更新而锁未更新时
   会直接拒绝。
3. **首次运行需要迭代。** 本工作流离线验证了 YAML 与脚本逻辑，
   但 arm 运行器上的完整编译链路以第一次真实运行为准；失败时看
   `cx60-diagnostics-*` 构件（build-logs/build-state/package.log）。
4. 内核 release 固定 `6.18.54-changxing60-bringup4`
   （CONFIG_LOCALVERSION + LOCALVERSION_AUTO=n），重建不变号，
   GUI"更新 OpenWrt"的同内核同版本更新路径保持可用。
5. 离线测试通过不等于真机验证；刷机与更新须按
   `docs/POWER-STANDBY-20261117.zh-CN.md` 的受控流程执行。