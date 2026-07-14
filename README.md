# 轨镜 RouteLens

基于游戏 `Client.txt` 的 Path of Exile / Path of Exile 2 **开荒路线计时**工具，无需 LiveSplit。

适合分段练习自己的开荒路线：随时保存、下次继续，而不是一次必须打完。

**当前版本：** `0.1.0`  
**仓库：** [github.com/orcwind/routelens](https://github.com/orcwind/routelens)

---

## 下载与使用（玩家）
1. 打开 [Releases](https://github.com/orcwind/routelens/releases)
2. 下载最新的 Windows 压缩包（例如 `RouteLens-v0.1.0-win64.zip`）
3. 解压后运行 `RouteLens.exe`

## 功能
- 类似 LiveSplit 的开荒计时

## 特点
- 一键导入自己的参考路线（PoE1 / PoE2）
- 支持简体中文 / 繁体中文 / 英文客户端（与游戏语言一致）
- 随时保存与继续，不必一次打完
- 进图切区自动推进节点

## 基本用法
1. 首次使用，**设置** → 选择对应游戏的 `Client.txt` → **导入路线**
2. 在参考路线列表中选中一条 → **新建 Run**， 会自动保存，下次想继续，点击路线，选择“继续”。
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

## 反馈
- B 站：[棱镜poe2lens](https://space.bilibili.com/35110142)
- 邮箱：`bazzarlens@gmail.com`
- 反馈时请尽量附上：游戏版本（PoE1 / PoE2）、客户端语言、复现步骤、截图，以及 `assist.log`

## 声明

非官方第三方工具，与 Grinding Gear Games 无关。按「现状」提供，使用风险自负。

## 开源协议

MIT

---

## 从源码运行（开发者）

仅给改代码 / 参与开发的人用，玩家请走上方 Releases。

```powershell
python -m pip install customtkinter pystray Pillow
python src/routelens_app.py
```

需要本机已安装 Python 3.10+。
