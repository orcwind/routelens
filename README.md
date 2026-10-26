# 轨镜 RouteLens

[中文](#中文) · [English](#english)

---

## 中文

基于游戏 `Client.txt` 的 Path of Exile / Path of Exile 2 **开荒路线计时**工具，无需 LiveSplit。

适合分段练习自己的开荒路线：随时保存、下次继续，而不是一次必须打完。

**当前版本：** `0.1.7`  
**仓库：** [github.com/orcwind/routelens](https://github.com/orcwind/routelens)

### 下载与使用（玩家）

1. 打开 [Releases](https://github.com/orcwind/routelens/releases)
2. 下载最新的 Windows 压缩包（例如 `RouteLens-v0.1.7-win64.zip`）
3. 解压后运行 `RouteLens.exe`

### 功能

- 类似 LiveSplit 的开荒计时

### 特点

- 一键导入自己的参考路线（PoE1 / PoE2）
- 支持简体中文 / 繁体中文 / 英文客户端（与游戏语言一致）
- 随时保存与继续，不必一次打完
- 进图切区自动推进节点
- 首次启动引导选择 Client.txt（中英双语）
- 启动时检查 GitHub Releases 自动更新（可在设置中关闭）
- 系统托盘常驻；`Shift+S` 一键鼠标穿透（面板不挡游戏点击）
- 关闭后重开自动恢复上次的 Run（进度与计时原样保留）
- 用户数据存放于 `%APPDATA%\RouteLens`：换目录 / 换机不丢设置与路线

### 基本用法

1. 首次使用，**设置** → 选择对应游戏的 `Client.txt` → **导入路线**
2. 在参考路线列表中选中一条 → **新建 Run**，会自动保存；下次想继续，点击路线，选择「继续」
3. 小键盘快捷键：

| 键 | 作用 |
|---|---|
| `0` | 开始计时 / 切区 |
| `2` | 跳过 |
| `8` | 撤销 |
| `3` | 暂停 |
| `5` | 重置 |

4. 关闭窗口会自动保存进度；下次选中同一路线点 **继续** 即可接着打。

日志可在 **设置 → 打开 Log / 打开 Log 目录** 找到（`assist.log`）。

### 反馈

- B 站：[棱镜poe2lens](https://space.bilibili.com/35110142)
- 邮箱：`bazzarlens@gmail.com`
- 反馈时请尽量附上：游戏版本（PoE1 / PoE2）、客户端语言、复现步骤、截图，以及 `assist.log`

### 声明

非官方第三方工具，与 Grinding Gear Games 无关。按「现状」提供，使用风险自负。

### 开源协议

MIT

### 从源码运行（开发者）

仅给改代码 / 参与开发的人用，玩家请走上方 Releases。

```powershell
python -m pip install customtkinter pystray Pillow
python src/routelens_app.py
```

需要本机已安装 Python 3.10+。

打包 Windows 可执行文件：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_routelens.ps1
```

产物：`dist/RouteLens/RouteLens.exe`，以及 `dist/RouteLens-v0.1.7-win64.zip`（可直接上传到 GitHub Releases）。  
自动更新依赖：Release **tag** 如 `v0.1.7`，资源名含 `win64.zip`。

---

## English

**RouteLens (轨镜)** is a Path of Exile / Path of Exile 2 **campaign route timer** driven by your game `Client.txt` — no LiveSplit required.

Built for practicing your own campaign route in sessions: save anytime, continue later, instead of clearing acts in one sitting.

**Version:** `0.1.7`  
**Repo:** [github.com/orcwind/routelens](https://github.com/orcwind/routelens)

### Download (players)

1. Open [Releases](https://github.com/orcwind/routelens/releases)
2. Download the latest Windows zip (e.g. `RouteLens-v0.1.7-win64.zip`)
3. Extract and run `RouteLens.exe`

No Python install needed for the release build.

### Features

- LiveSplit-style campaign timing

### Highlights

- One-click import of your own reference routes (PoE1 / PoE2)
- Works with Simplified Chinese / Traditional Chinese / English clients (matches your game language)
- Save and resume anytime — no need to finish in one run
- Auto-advance nodes when you change zones in-game
- First-time setup wizard with in-app EN / 中文 switch
- Optional startup check of GitHub Releases for auto-update (toggle in Settings)
- System tray resident; `Shift+S` toggles mouse click-through (panel never blocks game clicks)
- Reopening the app restores your last Run (progress and timer intact)
- User data lives in `%APPDATA%\RouteLens` — settings and routes survive moving the folder

### Basic usage

1. First time: **Settings** → pick the game’s `Client.txt` → **Import Routes**
2. Select a reference route → **New Run** (progress auto-saves). Later, select the route and click **Continue**
3. Numpad hotkeys:

| Key | Action |
|---|---|
| `0` | Start / split |
| `2` | Skip |
| `8` | Undo |
| `3` | Pause |
| `5` | Reset |

4. Closing the window saves progress; pick the same route and **Continue** next time.

Logs are available via **Settings → Open Log / Open Log Folder** (`assist.log`).

### Feedback

- Bilibili: [棱镜poe2lens](https://space.bilibili.com/35110142)
- Email: `bazzarlens@gmail.com`
- Please include: game (PoE1 / PoE2), client language, steps to reproduce, screenshots, and `assist.log`

### Disclaimer

Unofficial third-party tool, not affiliated with Grinding Gear Games. Provided as-is; use at your own risk.

### License

MIT

### Run from source (developers)

For contributors only. Players should use Releases above.

```powershell
python -m pip install customtkinter pystray Pillow
python src/routelens_app.py
```

Requires Python 3.10+ on your machine.

Build the Windows executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_routelens.ps1
```

Outputs: `dist/RouteLens/RouteLens.exe` and `dist/RouteLens-v0.1.7-win64.zip` (upload the zip to GitHub Releases).
