from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from routelens.gui import RouteLensApp
from routelens.tray_icon import set_windows_app_id


def main() -> None:
    # 必须在创建窗口前设置，任务栏才会用 RouteLens.exe / routelens.ico
    set_windows_app_id()
    app = RouteLensApp()
    if not app.run_startup():
        return
    app.run()


if __name__ == "__main__":
    main()
