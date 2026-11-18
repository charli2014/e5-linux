# 畅行60 GitHub Actions 编译与发布

工作流：`.github/workflows/changxing60-release.yml`。与 E5 的 `release.yml`
完全独立，互不影响；E5 发布流程不做任何改动。

## 流水线结构

| job | 运行器 | 内容 |
|---|---|---|
| `kernel` | ubuntu-24.04-arm | 公开内核源码 `Enceka/linux-lts-e5`（默认提交 `020b970e`，即本机登记的 UMS9620 供体基线）+ 引导包中的基线 config，跑 `devices/changxing60/build-kernel.py`（含 prepare-kernel 补丁与全部板级测试），产出内核交付 tar |
| `build` | ubuntu-24.04-arm | 还原引导输入 → `prepare-installers` 下载版本锁定的三平台安装器（sha256 + 源码指纹双校验）→ 导入 OpenWrt 25.12.5 armsr 基础镜像 → 省电/更新保留测试 → 编译 ModemManager/BlueZ/原生屏组件（带缓存）与 guarded block-mount → `sudo tools/build-release.py package --profiles changxing60`（唯一发布入口，Android 安装器由 input_check 自动构建）→ 校验 zip、写 SHA256SUMS 与发布说明 |
| `publish` | ubuntu-24.04 | 沿用 E5 的草稿 Release 流程：校验哈希 → 建草稿 → 上传 → 发布；已发布的 tag 拒绝覆盖 |

安装器不在 CI 从源码编译，而是走 `tools/installer-inputs.lock.json` 锁定的
上游已发布构件（`prepare-installers`，LOCAL-BUILD 的标准流程）。原因：
installer 子模块的测试套件在 GitHub 托管运行器上有平台缺陷（Windows
cp1252 编码/反斜杠路径语义，macOS 无 `os.listxattr`、/var 别名解析），
子模块仓库不在本 fork 名下、无法推送修复；锁定下载同样经过哈希与源码
指纹校验，不削弱验证。E5 的 `release.yml` 仍走源码编译，不受影响。

内核源码是公开仓库，**不需要公开任何厂商源码**。私有输入只有引导包
（见下），与 E5 的 `E5_CI_INPUTS_URL` 机制相同。

## 一次性准备（在构建机上执行）

引导包把本机登记的输入固化成哈希锁定的归档，供 CI 还原：

- `dumps/changxing60-stock/boot_a.img`、`misc-head.bin` → 只保留
  Android 头/vbmeta/footer 与 bootloader_control 的模板（剥离原厂内核与其余内容）；
- `{workspace}/kernels/m8/config` → UMS9620 基线 config（校验两个登记标记）；
- `{workspace}/base/e5` → 干净 base（必须含 `sbin/sysupgrade.openwrt`，
  不得含 wcnmodem.bin、opt/e5/android 等设备专属内容）；
- `work/e5-port/clean-openwrt-base.tar`、`work/wifi-sae`、`work/iwinfo-ap-scan`、
  `{workspace}/artifacts/lpac` → 打包前分别过各自 state 脚本的 inspect。

```sh
cd e5-linux
python3 tools/ci-inputs.py create --profile changxing60 \
  --workspace /home/kano/openwrt-build
# 产出 out/cx60-ci-inputs.tar.gz 与 out/cx60-ci-inputs.tar.gz.sha256
```

各输入路径都可以用 `--boot/--misc/--base-config/--base-dir/--defaults/
--wifi-apks/--iwinfo-apks/--lpac-apks` 覆盖。归档创建时即自检
（`inspect`），还原时先对 SHA-256 再逐项复检。

然后把归档放到一个固定 HTTPS 地址（例如本 fork 的一个专用 Release 资产，
或任何长期稳定的 HTTPS 下载点），在仓库
**Settings → Secrets and variables → Actions → Variables** 新建：

| 变量 | 值 |
|---|---|
| `E5_CX60_CI_INPUTS_URL` | 归档的 HTTPS 下载地址 |
| `E5_CX60_CI_INPUTS_SHA256` | `.sha256` 文件中的 64 位哈希 |

引导包不含厂商固件、完整原厂镜像或设备转储；boot/misc 模板只含启动
控制所需的最小结构。但它仍属于构建输入，放在自己控制的地址即可。

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

1. **引导包会过期。** wifi-sae / iwinfo / lpac / block-mount 的 inspect 与
   build-id 按仓库当前源码计算；改了这些源码后旧引导包会在 input_check
   被拒（报 source mismatch），需在构建机重新 `create` 并更新两个变量。
   基线 config、base、模板同理。
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