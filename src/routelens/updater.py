"""从 GitHub Releases 检查 / 下载 / 应用更新（仅打包版可自动替换）。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .paths import APP_ROOT, is_frozen
from .version import GITHUB_URL, VERSION

GITHUB_REPO = "orcwind/routelens"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"{GITHUB_URL}/releases"
USER_AGENT = f"RouteLens/{VERSION} (+{GITHUB_URL})"
ASSET_NAME_HINTS = ("win64.zip", "windows.zip", "routelens", ".zip")
# 安装包里可能有、但更新时绝不能覆盖到用户目录的顶层名
SKIP_TOP_LEVEL = frozenset({"config.json", "_update"})
# 用户数据 / 全部 data：更新过程中永不删除、永不覆盖
USER_DATA_REL_PATHS = (
    "config.json",
    "data",
)


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    name: str
    body: str
    html_url: str
    asset_name: str
    asset_url: str
    asset_size: int


def parse_version(text: str) -> tuple[int, ...]:
    cleaned = str(text or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def is_newer(remote: str, local: str = VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


def _http_json(url: str, *, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_asset(assets: list[dict]) -> dict | None:
    if not assets:
        return None
    lowered = []
    for item in assets:
        name = str(item.get("name") or "").lower()
        url = str(item.get("browser_download_url") or "")
        if not name.endswith(".zip") or not url:
            continue
        lowered.append((name, item))
    if not lowered:
        return None
    for hint in ("win64.zip", "win64", "windows", "routelens"):
        for name, item in lowered:
            if hint in name:
                return item
    return lowered[0][1]


def fetch_latest_release(*, timeout: float = 12.0) -> ReleaseInfo | None:
    """查询最新 Release；无 release / 网络失败返回 None。"""
    try:
        data = _http_json(RELEASES_API, timeout=timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    tag = str(data.get("tag_name") or "").strip()
    version = tag.lstrip("vV") or str(data.get("name") or "").strip().lstrip("vV")
    if not version:
        return None
    asset = _pick_asset(list(data.get("assets") or []))
    if asset is None:
        return None
    return ReleaseInfo(
        tag=tag or f"v{version}",
        version=version,
        name=str(data.get("name") or tag or version),
        body=str(data.get("body") or "").strip(),
        html_url=str(data.get("html_url") or RELEASES_PAGE),
        asset_name=str(asset.get("name") or ""),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_size=int(asset.get("size") or 0),
    )


def check_for_update(*, timeout: float = 12.0) -> ReleaseInfo | None:
    info = fetch_latest_release(timeout=timeout)
    if info is None:
        return None
    if not is_newer(info.version, VERSION):
        return None
    return info


def download_asset(url: str, dest: Path, *, timeout: float = 120.0, progress=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)


def _find_payload_root(extract_dir: Path) -> Path:
    """zip 内可能是 RouteLens/ 目录，也可能直接是 exe。"""
    direct = extract_dir / "RouteLens.exe"
    if direct.is_file():
        return extract_dir
    nested = extract_dir / "RouteLens"
    if (nested / "RouteLens.exe").is_file():
        return nested
    for child in extract_dir.iterdir():
        if child.is_dir() and (child / "RouteLens.exe").is_file():
            return child
    raise FileNotFoundError("zip 中未找到 RouteLens.exe")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def _sanitize_payload(payload_dir: Path) -> None:
    """去掉安装包中的 data/config，更新时绝不触碰用户路线/记录/静态数据/配置。"""
    for rel in USER_DATA_REL_PATHS:
        _remove_path(payload_dir / Path(rel))
    for name in SKIP_TOP_LEVEL:
        _remove_path(payload_dir / name)


def _write_apply_script(
    *,
    install_dir: Path,
    payload_dir: Path,
    exe_name: str,
) -> Path:
    """
    主程序退出后只覆盖程序文件；
    绝不删除/覆盖用户 config、routes、results、active_run、日志。
    """
    update_dir = install_dir / "_update"
    update_dir.mkdir(parents=True, exist_ok=True)
    script = update_dir / "apply_update.bat"
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f'set "INSTALL={install_dir}"',
        f'set "PAYLOAD={payload_dir}"',
        f'set "EXE={exe_name}"',
        "ping -n 3 127.0.0.1 >nul",
        ":wait",
        'tasklist /FI "IMAGENAME eq %EXE%" 2>nul | find /I "%EXE%" >nul',
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto wait",
        ")",
        'REM user data lives in %APPDATA%\\RouteLens now; exe dir only has program files',
        'robocopy "%PAYLOAD%" "%INSTALL%" /E /XD data _update /XF config.json /R:2 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np',
        'start "" "%INSTALL%\\%EXE%"',
        "endlocal",
        "exit /b 0",
    ]
    script.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="ignore")
    return script


def prepare_and_launch_update(release: ReleaseInfo, *, install_dir: Path | None = None) -> Path:
    """
    下载并解压到临时目录，写 bat，启动 bat。
    调用方应随后退出主程序。
    返回 bat 路径。
    """
    if not is_frozen():
        raise RuntimeError("auto-update only supported for packaged builds")
    root = (install_dir or APP_ROOT).resolve()
    work = root / "_update"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / release.asset_name
    extract_dir = work / "extract"
    payload_copy = work / "payload"
    download_asset(release.asset_url, zip_path)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    payload = _find_payload_root(extract_dir)
    if payload_copy.exists():
        shutil.rmtree(payload_copy, ignore_errors=True)
    shutil.copytree(payload, payload_copy)
    _sanitize_payload(payload_copy)
    exe_name = Path(sys.executable).name if is_frozen() else "RouteLens.exe"
    script = _write_apply_script(
        install_dir=root,
        payload_dir=payload_copy,
        exe_name=exe_name,
    )
    flags = 0x00000008 | 0x00000200
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        cwd=str(work),
        close_fds=True,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return script


def open_releases_page() -> None:
    import webbrowser

    webbrowser.open(RELEASES_PAGE)


def run_check_in_thread(callback, *, timeout: float = 12.0) -> None:
    """后台查更新；callback(info|None, error|None) 在工作线程调用。"""

    def worker() -> None:
        try:
            callback(check_for_update(timeout=timeout), None)
        except Exception as exc:  # noqa: BLE001
            callback(None, exc)

    threading.Thread(target=worker, daemon=True).start()
