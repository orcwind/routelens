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
        "setup_title": "首次设置",
        "setup_welcome": "欢迎使用 {app}",
        "setup_hint": "请选择 PoE 或 PoE2 的 Client.txt。\n位置通常在：游戏目录\\logs\\Client.txt",
        "setup_browse": "浏览选择 Client.txt",
        "setup_found_title": "已选择游戏日志",
        "setup_use": "使用这个",
        "setup_reselect": "重新选择",
        "setup_manual": "手动选择",
        "setup_pick_title": "选择 Client.txt",
        "setup_bad_path": "路径无效",
        "setup_bad_path_detail": "找不到文件：\n{path}",
        "setup_exit_title": "退出",
        "setup_exit_confirm": "未完成设置将无法使用。\n确定退出？",
        "update_title": "发现新版本",
        "update_body": "当前版本：{current}\n最新版本：{latest}\n\n是否下载并安装更新？\n（保留你的路线、练习记录与设置；安装后自动重启）",
        "update_downloading": "正在下载更新，请稍候…",
        "update_ready": "下载完成，程序将重启以完成安装。",
        "update_fail": "更新失败",
        "update_fail_detail": "{exc}",
        "update_latest": "已是最新版本（{version}）。",
        "update_none": "暂时无法检查更新（网络或尚未发布 Release）。",
        "update_dev_only": "开发模式不能自动覆盖安装。已打开 Releases 页面，请手动下载。",
        "check_updates_btn": "检查更新",
        "check_updates_toggle": "启动时检查更新",
        "new_run": "新建 Run",
        "continue": "继续",
        "select_route": "选择一条参考路线",
        "no_routes": "暂无参考路线",
        "no_routes_hint": "请在右上角「设置」中选择 Client.txt 并导入路线。",
        "no_continue": "这条路线没有可继续的进度。",
        "pick_route_first": "请先选择一条参考路线。",
        "free_run": "自由路线（记录新路线）",
        "free_run_poe1": "空白路线 · Path of Exile",
        "free_run_poe2": "空白路线 · Path of Exile 2",
        "need_client_for_game_title": "缺少 Client.txt",
        "need_client_for_game": "尚未找到 {game} 的 Client.txt。请先在「设置」里为这个游戏选择日志路径。",
        "free_run_hint": "不选路线直接开始：节点名与时间全部按实际进图记录。",
        "save_as_route": "存路线",
        "intro_title": "介绍 — 轨镜 RouteLens",
        "about": "关于",
        "bug": "Bug 反馈",
        "open_log": "打开 Log",
        "open_log_folder": "打开 Log 目录",
        "save_close": "保存并关闭",
        "back_routes": "返回路线选择",
        "back_short": "返回",
        "press_0": "点击/按 0 开始计时",
        "waiting_area": "等待进图",
        "campaign_over": "剧情已结束 · 计时已暂停",
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
        "view_node": "节点",
        "view_act": "幕",
        "view_toggle": "节点/幕",
        "view_switch_act": "切到幕",
        "view_switch_node": "切到节点",
        "act_view_hint": "按幕计时",
        "node_view_hint": "按节点计时",
        "act_endgame": "终局",
        "act_interlude": "間歇",
        "hotkeys": "0 切区 · 2 跳过 · 8 撤销 · 3 暂停 · 4 节点/幕 · 5 重置 · 9 极简",
        "hk_0": "0 切区",
        "hk_2": "2 跳过",
        "hk_8": "8 撤销",
        "hk_3": "3 暂停",
        "hk_4": "4 节点/幕",
        "hk_5": "5 重置",
        "hk_9": "9 极简",
        "hk_click_through": "Shift+S 穿透",
        "click_through_on": "已穿透",
        "click_through_off": "穿透",
        "click_through_unavailable": "热键被占用",
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
        "import_msg_unfinished": "\n\n⚠ 以下角色未通关（日志中无开荒终点），已按现有节点导入，路线可能不完整：{names}\n建议通关后用新日志重新导入。",
        "import_msg_locale": "\n\n识别日志语言：{locale}",
        "import_msg_game": "\n\n识别日志游戏：{game}",
        "import_msg_log": "\n\n详细日志：{path}",
        "open_fail_detail": "{exc}\n\n路径：{path}",
        "client_not_found": "未找到 Client.txt，请在设置中选择路径。",
        "intro_body": """轨镜 RouteLens

基于游戏 Client.txt 的开荒路线计时工具，无需 LiveSplit。
支持 Path of Exile / Path of Exile 2。

一、工具特点
1. 从游戏 Client.txt 读取你自己的开荒路线，真实可复现。
2. 节点名直接使用 Client.txt 中的原文（简中 / 繁中 / 英文随游戏客户端）。
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

小键盘速查：0 切区 · 2 跳过 · 8 撤销 · 3 暂停 · 5 重置 · 9 极简
全局热键：Shift+S 鼠标穿透（面板不挡游戏点击，显示不中断）
""",
    },
    UI_LANG_EN: {
        "app_name": "轨镜 RouteLens",
        "ref_routes": "Reference Routes",
        "settings": "Settings",
        "intro": "Intro",
        "lang_btn": "中文",
        "setup_title": "First-time Setup",
        "setup_welcome": "Welcome to {app}",
        "setup_hint": "Select Client.txt for Path of Exile or Path of Exile 2.\nUsually at: GameFolder\\logs\\Client.txt",
        "setup_browse": "Browse for Client.txt",
        "setup_found_title": "Game log selected",
        "setup_use": "Use this",
        "setup_reselect": "Choose again",
        "setup_manual": "Manual select",
        "setup_pick_title": "Select Client.txt",
        "setup_bad_path": "Invalid path",
        "setup_bad_path_detail": "File not found:\n{path}",
        "setup_exit_title": "Quit",
        "setup_exit_confirm": "Setup is incomplete and the app cannot run.\nQuit anyway?",
        "update_title": "Update available",
        "update_body": "Current: {current}\nLatest: {latest}\n\nDownload and install now?\n(Your routes, run records, and settings are kept; the app will restart)",
        "update_downloading": "Downloading update, please wait…",
        "update_ready": "Download complete. The app will restart to finish installing.",
        "update_fail": "Update failed",
        "update_fail_detail": "{exc}",
        "update_latest": "You are on the latest version ({version}).",
        "update_none": "Could not check for updates (network issue or no Release yet).",
        "update_dev_only": "Dev builds cannot auto-install. Opened the Releases page for a manual download.",
        "check_updates_btn": "Check for updates",
        "check_updates_toggle": "Check for updates on startup",
        "new_run": "New Run",
        "continue": "Continue",
        "select_route": "Select a reference route",
        "no_routes": "No routes yet",
        "no_routes_hint": "Open Settings (top-right), pick Client.txt, then Import Routes.",
        "no_continue": "No saved progress for this route.",
        "pick_route_first": "Please select a reference route first.",
        "free_run": "Free Run (record a new route)",
        "free_run_poe1": "Blank Route · Path of Exile",
        "free_run_poe2": "Blank Route · Path of Exile 2",
        "need_client_for_game_title": "Client.txt not found",
        "need_client_for_game": "No Client.txt selected for {game}. Choose its log path in Settings first.",
        "free_run_hint": "Start without a route: every node name and time is recorded from the areas you enter.",
        "save_as_route": "Save route",
        "intro_title": "Intro — 轨镜 RouteLens",
        "about": "About",
        "bug": "Bug Report",
        "open_log": "Open Log",
        "open_log_folder": "Open Log Folder",
        "save_close": "Save & Close",
        "back_routes": "Back to Routes",
        "back_short": "Back",
        "press_0": "Click / Press 0 to start",
        "waiting_area": "Waiting for area",
        "campaign_over": "Campaign complete · timer paused",
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
        "view_node": "Node",
        "view_act": "Act",
        "view_toggle": "Node/Act",
        "view_switch_act": "Act view",
        "view_switch_node": "Node view",
        "act_view_hint": "Timing by act",
        "node_view_hint": "Timing by node",
        "act_endgame": "Endgame",
        "act_interlude": "Interlude",
        "hotkeys": "0 Split · 2 Skip · 8 Undo · 3 Pause · 4 Node/Act · 5 Reset · 9 Minimal",
        "hk_0": "0 Split",
        "hk_2": "2 Skip",
        "hk_8": "8 Undo",
        "hk_3": "3 Pause",
        "hk_4": "4 Node/Act",
        "hk_5": "5 Reset",
        "hk_9": "9 Minimal",
        "hk_click_through": "Shift+S Click-Through",
        "click_through_on": "Click-Through On",
        "click_through_off": "Click-Through",
        "click_through_unavailable": "Hotkey in use",
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
        "import_msg_unfinished": "\n\n⚠ These characters have not finished the campaign (no campaign end in log); imported as-is and may be incomplete: {names}\nRe-import with a newer log after finishing the campaign.",
        "import_msg_locale": "\n\nDetected log locale: {locale}",
        "import_msg_game": "\n\nDetected game: {game}",
        "import_msg_log": "\n\nDetailed log: {path}",
        "open_fail_detail": "{exc}\n\nPath: {path}",
        "client_not_found": "Client.txt not found. Please set the path in Settings.",
        "intro_body": """轨镜 RouteLens

Campaign route timer driven by your game Client.txt — no LiveSplit required.
Supports Path of Exile and Path of Exile 2.

1. Features
1. Import your own campaign routes from Client.txt — real runs you can retime.
2. Node names come from Client.txt as-is (Simplified / Traditional Chinese / English follows your game client).
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

Hotkeys: 0 split · 2 skip · 8 undo · 3 pause · 5 reset · 9 minimal
Global: Shift+S toggle click-through (panel won't block in-game clicks, display keeps running)
""",
    },
}


def t(lang: str, key: str) -> str:
    table = STRINGS.get(lang) or STRINGS[UI_LANG_ZH]
    return table.get(key) or STRINGS[UI_LANG_ZH].get(key, key)
