"""轨镜版本与关于信息。"""

VERSION = "0.1.2"
APP_NAME = "轨镜"
APP_NAME_EN = "RouteLens"
APP_DISPLAY = f"{APP_NAME} {APP_NAME_EN}"
AUTHOR = "棱镜（poe2lens）"
LICENSE = "MIT"
GITHUB_URL = "https://github.com/orcwind/routelens"
BILIBILI_URL = "https://space.bilibili.com/35110142"
CONTACT_EMAIL = "bazzarlens@gmail.com"

BUG_FEEDBACK_TEXT = f"""如有 Bug，请与 B 站「棱镜poe2lens」联系：
{BILIBILI_URL}

或将 assist.log 发送至：
{CONTACT_EMAIL}

日志路径可在「设置 → 打开 Log / 打开 Log 目录」直接打开。
反馈时若能附上：游戏版本（PoE1 / PoE2）、语言客户端、复现步骤与截图，会更快定位问题。

感谢反馈。
"""

BUG_FEEDBACK_TEXT_EN = f"""If you hit a bug, contact Bilibili「棱镜poe2lens」:
{BILIBILI_URL}

Or send assist.log to:
{CONTACT_EMAIL}

Open the log via Settings → Open Log / Open Log Folder.
Please include game (PoE1 / PoE2), client language, steps to reproduce, and screenshots when possible.

Thanks!
"""

ABOUT_TEXT = f"""{APP_DISPLAY}  v{VERSION}

用途：
基于游戏 Client.txt 的开荒路线计时工具，无需 LiveSplit。
支持 Path of Exile / Path of Exile 2，
以及简体中文 / 繁体中文 / 英文客户端日志。

制作者：{AUTHOR}
版本：{VERSION}
开源协议：{LICENSE}
B 站：{BILIBILI_URL}
邮箱：{CONTACT_EMAIL}
GitHub：{GITHUB_URL}

声明：
· 非官方第三方工具，与 Grinding Gear Games 无关
· 仅读取本地 Client.txt，不修改游戏文件、不注入进程
· 按「现状」提供，使用风险自负

贡献：
欢迎在 GitHub 提 Issue / Pull Request。
"""

ABOUT_TEXT_EN = f"""{APP_DISPLAY}  v{VERSION}

Purpose:
Client.txt–based campaign route timer — no LiveSplit required.
Supports Path of Exile / Path of Exile 2,
and Simplified Chinese / Traditional Chinese / English client logs.

Author: {AUTHOR}
Version: {VERSION}
License: {LICENSE}
Bilibili: {BILIBILI_URL}
Email: {CONTACT_EMAIL}
GitHub: {GITHUB_URL}

Disclaimer:
· Unofficial third-party tool, not affiliated with Grinding Gear Games
· Reads local Client.txt only — does not modify game files or inject into the process
· Provided as-is; use at your own risk

Contributing:
Issues and Pull Requests on GitHub are welcome.
"""
