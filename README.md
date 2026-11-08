# Vestel Tab Z2 (MT6765) 内核云端构建

用 GitHub Actions 把 4.19.325 内核编译成可直接 `fastboot flash boot` 的 `boot.img`。

设备：Vestel Tab Z2 / EKVATOR，MediaTek MT6765 (MT8768)，原厂 Android 11，原厂内核 4.19.127。

---

## 这一版能做到什么、做不到什么

| | 状态 |
|---|---|
| 云端编译 4.19.325 内核（原厂配置为基准） | ✅ |
| 打出与原厂结构一致的 boot.img | ✅ 打包器已通过逐字节零差异验证 |
| 内核能启动、ADB 可连、能看 dmesg | ✅ 大概率 |
| **屏幕点亮** | ❌ **不会亮** |
| 触摸、相机、指纹 | ❌ 不工作 |
| Android 16 | ❌ 完全到不了 |

**为什么屏不亮**：原厂面板驱动 `nt51021h_wuxga_vdo_oncell_boe`（1200×1920，Novatek NT51021，270°）在这棵源码树里不存在——树里只有 Redmi 9A 家族的 10 个 720p 手机屏。LCM 初始化序列是硬编码在 C 驱动里的（`CONFIG_MTK_LCM_DEVICE_TREE_SUPPORT` 未启用），无法从 DTB 补，也无法凭空猜到寄存器值。

因此本仓库把 `CONFIG_CUSTOM_KERNEL_LCM` 指向树内最接近的 `nt36525b_vdo_hdp_boe_xinli`（同为 Novatek IC），目的是**让编译通过**，不是让屏幕亮。

**这一版的价值**：验证「原厂配置能在 4.19.325 上编过」「打包流程正确」「内核能在真机上进入 early stage」。这是后续移植面板驱动的地基。

---

## 仓库结构

```
.github/workflows/build.yml   12 步流水线
configs/ekvator.config        原厂完整内核配置（5402 行，从 boot.img 的 IKCONFIG 段提取）
prebuilt/dtb                  本机设备树 107,563 字节（含 MTK 64 字节封装头）
prebuilt/ramdisk.gz           本机 ramdisk 1,323,076 字节（已含 Magisk）
scripts/pack_bootimg.py       boot header v0–v2 打包器（纯标准库）
```

### 配置改动的 5 处，为什么改

| 配置项 | 原厂 | 改为 | 原因 |
|---|---|---|---|
| `CONFIG_CUSTOM_KERNEL_LCM` | `nt51021h_wuxga_vdo_oncell_boe` | `nt36525b_vdo_hdp_boe_xinli` | 原面板驱动树内不存在，不改则 `make` 直接报目录不存在 |
| `CONFIG_BATTERY_MT6359` | `=m` | `=y` | 原来是模块，内核升级后 vermagic 变化导致 vendor 里的 `.ko` 被 modversions 拒绝加载，电量会异常 |
| `CONFIG_SND_SOC_MT6359_ACCDET` | `=m` | `=y` | 同上，耳机检测会失效 |
| `CONFIG_DEBUG_INFO` | `=y` | 关闭 | `Image` 不含调试段，关掉只影响 `vmlinux`，可省约 40% 编译时间和数 GB 磁盘 |
| `CONFIG_LOCALVERSION_AUTO` | `=y` | 关闭 | 否则版本串带 git 描述（`4.19.325-gxxxxxx`），产物不可复现 |

其余 5392 行**原样保留**，包括 `CONFIG_MTK_PLATFORM="mt6765"`、`CONFIG_MACH_MT6765=y`、`CONFIG_MTK_FB=y`、`CONFIG_MTK_LCM_PHYSICAL_ROTATION="270"`、`CONFIG_LCM_WIDTH="1200"`、`CONFIG_LCM_HEIGHT="1920"`。

---

## 怎么用

### 1. 建仓库并上传

**推荐用电脑**（手机上 `.github` 是隐藏目录，网页上传会丢）：

```bash
cd ekvator-a
git init
git add -A
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

仓库必须 **Public**。私有仓库跑 Actions 会消耗额度（每月 2000 分钟，本流程单次约 60–90 分钟）。

### 2. 运行

Actions 页面 → 左侧 **Build Kernel** → 右上 **Run workflow** → 绿色按钮。

手机上左侧列表被折叠在左上角的 ☰ 菜单里，直接打开这个链接更快：

```
https://github.com/<用户名>/<仓库名>/actions/workflows/build.yml
```

### 3. 取产物

约 60–90 分钟后（4 核 runner 编 MTK 全内建内核，比通用内核慢），页面底部 Artifacts 出现 `boot-image`，内含：

- `boot.img` — 可直接刷的完整镜像
- `Image.gz` — 仅内核，备用

---

## 刷之前的必读

### 必须有的退路

| 条件 | 说明 |
|---|---|
| TWRP 在设备上 | 首选。TWRP 走独立显示通路，黑屏也能进，能刷回原厂镜像 |
| 或 fastboot 可用 + 有电脑 | 次选。黑屏后靠 `fastboot flash boot` 回滚 |
| 两者都没有 | **不要刷**。屏不亮是预期结果，没有退路等于变砖 |

### 一定要先备份原厂 boot

```bash
adb shell su -c "dd if=/dev/block/by-name/boot of=/sdcard/boot_stock.img"
adb pull /sdcard/boot_stock.img
```

### 刷写

```bash
fastboot flash boot boot.img
fastboot reboot
```

如果 LK 因 AVB 拒绝启动（本镜像未签名）：

```bash
fastboot flash vbmeta --disable-verity --disable-verification vbmeta.img
```

### 预期现象

刷完大概率是**黑屏**，但设备其实在跑：

```bash
adb devices                 # 可能能连上
adb shell dmesg | grep -i lcm
```

看到 `lcm` 相关报错、或 `panel not found`，说明内核起来了、只是屏没驱动。这正是本版预期。如果连 ADB 都连不上、或无限重启，说明是更深层的问题（配置或 DTB 不匹配），刷回 `boot_stock.img`。

---

## 已知会出现的编译/运行问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `unknown symbol CONFIG_TOUCHSCREEN_MTK_GSLX68X` | 该触摸驱动树内不存在，Kconfig 丢弃 | 仅 warning，不影响编译，触摸不工作 |
| vermagic 与 vendor `.ko` 不匹配 | 4.19.127 → 4.19.325 必然变化 | 已在配置里把两个 PMIC 模块改为内建 |
| 编译超过 5 小时 | 全内建 MTK 内核代码量大 | 把 `timeout-minutes` 调高，或加 `actions/cache` 缓存 ccache |
| `Clone clang` 失败 | 仓库名写错 | 已固定为 `r416183b`（clang 14.0.7），与原厂 clang 11 同一系谱 |

---

## 下一步

屏幕要点亮，只有一条路：把上游 `panel-novatek-nt51021.c`（2026 年 9 月进 mainline，覆盖 1200×1920 的 NT51021 面板）的 init 序列转写成 MTK `LCM_DRIVER` 格式，放到 `drivers/misc/mediatek/lcm/` 下，然后把 `CONFIG_CUSTOM_KERNEL_LCM` 指回 `nt51021h_wuxga_vdo_oncell_boe`。这需要真机反复试，不是改配置能完成的。

---

## 许可

`scripts/` 与 `.github/` 为本仓库编写，GPL-2.0。
`configs/ekvator.config` 提取自设备原厂内核构建产物。
`prebuilt/dtb`、`prebuilt/ramdisk.gz` 来自设备原厂固件，版权归原始厂商，仅用于该设备的系统构建与恢复。
