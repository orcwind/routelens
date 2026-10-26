from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from routelens import single_instance
from routelens.gui import RouteLensApp
from routelens.tray_icon import set_windows_app_id


def main() -> None:
    # 必须在创建窗口前设置，任务栏才会用 RouteLens.exe / routelens.ico
    set_windows_app_id()
    # 单实例：第二个进程会把已运行实例从托盘唤醒后退出。
    # 否则两份进程抢 RegisterHotKey(Shift+S)，后启动的那份永远注册失败 → 热键「失效」。
    if not single_instance.acquire_single_instance():
        if not single_instance.signal_existing_instance():
            single_instance.activate_window_fallback()
        return
    activation_event = single_instance.create_activation_event()
    app = RouteLensApp()
    if not app.run_startup():
        return
    app.attach_single_instance_activation(activation_event)
    app.run()


if __name__ == "__main__":
    main()
