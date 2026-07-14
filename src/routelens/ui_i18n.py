"""轨镜界面文案（简体中文 / English）。"""

from __future__ import annotations

UI_LANG_ZH = "zh"
UI_LANG_EN = "en"

STRINGS: dict[str, dict[str, str]] = {
    UI_LANG_ZH: {
        "app_name": "轨镜 RouteLens",
        "ref_routes": "参考路线",
        "settings": "设置",
        "intro": "介绍",
        "lang_btn": "EN",
        "new_run": "新建 Run",
        "continue": "继续",
        "select_route": "选择一条参考路线",
        "no_routes": "暂无参考路线",
        "no_routes_hint": "请在右上角「设置」中选择 Client.txt 并导入路线。",
        "no_continue": "这条路线没有可继续的进度。",
        "pick_route_first": "请先选择一条参考路线。",
        "intro_title": "介绍 — 轨镜 RouteLens",
        "about": "关于",
        "bug": "Bug 反馈",
        "open_log": "打开 Log",
        "open_log_folder": "打开 Log 目录",
        "save_close": "保存并关闭",
        "back_routes": "返回路线选择",
        "press_0": "按 0 开始计时",
        "favorite": "收藏",
        "unfavorite": "取消收藏",
        "rename": "重命名",
        "delete": "删除",
        "tray_show": "显示窗口",
        "tray_close": "关闭",
        "minimal": "极简",
        "col_node": "节点",
        "col_time": "用时",
        "col_ref": "参考",
        "col_delta": "差值",
        "col_total": "总时间",
        "hotkeys": "0 切区 · 2 跳过 · 8 撤销 · 3 暂停 · 5 重置",
        "undo_reset": "撤销重置",
        "reset_confirm": "确定重置？进度与计时将归零。\n\n重置前会自动备份；误触后可点底部「撤销重置」找回。",
        "undo_reset_none": "没有可恢复的重置备份。",
        "undo_reset_confirm": "恢复到最近一次重置前的进度？\n当前已重置的空白进度会被覆盖。",
        "undo_reset_ok": "已恢复重置前的进度，按 0 开始计时。",
        "reset_title": "重置",
        "exit_minimal": "退出极简模式",
        "close": "关闭",
        "game_poe1": "流放之路",
        "game_poe2": "流放之路 2",
        "browse_client": "选择 Client",
        "import_routes": "导入路线",
        "client_hint": "Client.txt 通常位置为：游戏目录\\logs\\Client.txt",
        "pick_client_title": "选择 {game} Client.txt",
        "import_need_client": "请先选择有效的 Client.txt。",
        "import_fail": "导入失败",
        "import_fail_title": "无法导入",
        "analyze_done": "分析完成",
        "open_log_empty": "尚未生成日志文件。运行一段时间后再试。",
        "open_log_folder_empty": "尚未初始化日志目录。",
        "open_fail": "打开失败",
        "copied": "已复制",
        "copied_bug": "反馈说明已复制到剪贴板。",
        "copy_all": "复制全部",
        "analyze_fail": "无法分析",
        "read_fail": "读取失败",
        "tip": "提示",
        "import_msg_recent": "从 Client.txt 末尾读取\n\n原始片段：{sessions} 次（每次 Client 启动算一段）\n按角色合并：{merged} 条候选\n导入完整开荒：{routes} 条",
        "import_msg_full": "发现 {sessions} 次开荒记录\n按角色合并：{merged} 条候选\n生成 {routes} 条参考路线",
        "import_msg_zero": "\n\n未导入路线。常见原因：\n· 日志被 Client 启动标记拆成很多短片段\n· 合并后仍不足 35 个节点或章节跨度不够\n请打开日志查看每条候选的 reject_reason。",
        "import_msg_locale": "\n\n识别日志语言：{locale}",
        "import_msg_log": "\n\n详细日志：{path}",
        "open_fail_detail": "{exc}\n\n路径：{path}",
        "client_not_found": "未找到 Client.txt，请在设置中选择路径。",
        "intro_body": """轨镜 RouteLens

基于游戏 Client.txt 的开荒路线计时工具，无需 LiveSplit。
支持 Path of Exile / Path of Exile 2。

一、工具特点
1. 从游戏 Client.txt 读取你自己的开荒路线，真实可复现。
2. 识别与显示语言跟随客户端（简体中文 / 繁体中文 / 英文）。
3. 未完成进度可随时保存，下次一键继续。

二、使用流程
首次使用：
· 打开「设置」→ 选择对应游戏的 Client.txt →「导入路线」

日常计时：
· 在路线页选中一条路线 →「新建 Run」
· 小键盘 0：开始计时 / 切区
· 进游戏切换场景时，轨镜会自动推进节点

随时关闭会自动保存进度。
下次选中同一路线，点「继续」即可接着上次的时间与节点继续。

小键盘速查：0 切区 · 2 跳过 · 8 撤销 · 3 暂停 · 5 重置
""",
    },
    UI_LANG_EN: {
        "app_name": "轨镜 RouteLens",
        "ref_routes": "Reference Routes",
        "settings": "Settings",
        "intro": "Intro",
        "lang_btn": "中文",
        "new_run": "New Run",
        "continue": "Continue",
        "select_route": "Select a reference route",
        "no_routes": "No routes yet",
        "no_routes_hint": "Open Settings (top-right), pick Client.txt, then Import Routes.",
        "no_continue": "No saved progress for this route.",
        "pick_route_first": "Please select a reference route first.",
        "intro_title": "Intro — 轨镜 RouteLens",
        "about": "About",
        "bug": "Bug Report",
        "open_log": "Open Log",
        "open_log_folder": "Open Log Folder",
        "save_close": "Save & Close",
        "back_routes": "Back to Routes",
        "press_0": "Press 0 to start",
        "favorite": "Favorite",
        "unfavorite": "Unfavorite",
        "rename": "Rename",
        "delete": "Delete",
        "tray_show": "Show Window",
        "tray_close": "Quit",
        "minimal": "Minimal",
        "col_node": "Node",
        "col_time": "Time",
        "col_ref": "Ref",
        "col_delta": "Diff",
        "col_total": "Total",
        "hotkeys": "0 Split · 2 Skip · 8 Undo · 3 Pause · 5 Reset",
        "undo_reset": "Undo Reset",
        "reset_confirm": "Reset timer and progress to zero?\n\nA backup is saved first; use “Undo Reset” at the bottom if this was a mistake.",
        "undo_reset_none": "No reset backup to restore.",
        "undo_reset_confirm": "Restore progress from before the last reset?\nThe blank run after reset will be overwritten.",
        "undo_reset_ok": "Restored. Press 0 to start the timer.",
        "reset_title": "Reset",
        "exit_minimal": "Exit Minimal",
        "close": "Quit",
        "game_poe1": "Path of Exile",
        "game_poe2": "Path of Exile 2",
        "browse_client": "Select Client",
        "import_routes": "Import Routes",
        "client_hint": "Client.txt is usually at: GameFolder\\logs\\Client.txt",
        "pick_client_title": "Select {game} Client.txt",
        "import_need_client": "Please select a valid Client.txt first.",
        "import_fail": "Import failed",
        "import_fail_title": "Cannot import",
        "analyze_done": "Import finished",
        "open_log_empty": "No log file yet. Run for a while and try again.",
        "open_log_folder_empty": "Log folder is not initialized yet.",
        "open_fail": "Failed to open",
        "copied": "Copied",
        "copied_bug": "Bug report text copied to clipboard.",
        "copy_all": "Copy all",
        "analyze_fail": "Cannot analyze",
        "read_fail": "Read failed",
        "tip": "Notice",
        "import_msg_recent": "Read from the end of Client.txt\n\nRaw sessions: {sessions} (each Client launch is one segment)\nMerged by character: {merged} candidates\nImported full campaigns: {routes}",
        "import_msg_full": "Found {sessions} campaign session(s)\nMerged by character: {merged} candidates\nCreated {routes} reference route(s)",
        "import_msg_zero": "\n\nNo routes imported. Common reasons:\n· Log was split into many short fragments by Client launches\n· After merge still under 35 nodes or chapter span is too small\nCheck assist.log for each candidate’s reject_reason.",
        "import_msg_locale": "\n\nDetected log locale: {locale}",
        "import_msg_log": "\n\nDetailed log: {path}",
        "open_fail_detail": "{exc}\n\nPath: {path}",
        "client_not_found": "Client.txt not found. Please set the path in Settings.",
        "intro_body": """轨镜 RouteLens

Campaign route timer driven by your game Client.txt — no LiveSplit required.
Supports Path of Exile and Path of Exile 2.

1. Features
1. Import your own campaign routes from Client.txt — real runs you can retime.
2. Detection follows the client language (Simplified Chinese / Traditional Chinese / English).
3. Save unfinished progress anytime and continue later in one click.

2. How to use
First time:
· Open Settings → select Client.txt for your game → Import Routes

Daily timing:
· Select a route → New Run
· Numpad 0: start timer / split
· When you change zones in-game, 轨镜 advances nodes automatically

Closing the app auto-saves progress.
Next time, select the same route and click Continue to resume time and node index.

Hotkeys: 0 split · 2 skip · 8 undo · 3 pause · 5 reset
""",
    },
}


def t(lang: str, key: str) -> str:
    table = STRINGS.get(lang) or STRINGS[UI_LANG_ZH]
    return table.get(key) or STRINGS[UI_LANG_ZH].get(key, key)
