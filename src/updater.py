"""自动更新模块：检查GitHub Releases新版本，下载installer并静默安装"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


class AutoUpdater:
    """检查并安装GitHub Release新版本"""

    def __init__(self, repo: str, current_version: str):
        """
        Args:
            repo: GitHub仓库，格式 "owner/repo"
            current_version: 当前版本号，如 "1.0.0"
        """
        self.repo = repo
        self.current_version = current_version
        self.api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    def check_update(self) -> dict:
        """检查是否有新版本

        Returns:
            dict: {
                "has_update": bool,
                "latest_version": str,
                "download_url": str or None,
                "release_notes": str,
            }
        """
        result = {
            "has_update": False,
            "latest_version": self.current_version,
            "download_url": None,
            "release_notes": "",
        }
        try:
            req = urllib.request.Request(
                self.api_url,
                headers={
                    "User-Agent": "LiveCompanion-Updater/1.0",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latest = data.get("tag_name", "").removeprefix("v")
            result["latest_version"] = latest
            result["release_notes"] = data.get("body", "")

            # 版本号比较
            if self._compare_versions(latest, self.current_version) > 0:
                result["has_update"] = True
                # 找installer asset
                for asset in data.get("assets", []):
                    name = asset.get("name", "")
                    if name.endswith(".exe") and ("Setup" in name or "setup" in name or "install" in name.lower()):
                        result["download_url"] = asset.get("browser_download_url")
                        break
                # 如果没找到指定的installer，用第一个exe asset
                if not result["download_url"]:
                    for asset in data.get("assets", []):
                        if asset.get("name", "").endswith(".exe"):
                            result["download_url"] = asset.get("browser_download_url")
                            break

        except Exception as api_err:
            # API 不可用（常见：匿名限流 403 rate limit、网络超时）时，
            # 用 releases/latest 的 302 重定向兜底拿版本号，不受 API 配额限制
            try:
                latest = self._latest_tag_via_redirect()
                result["latest_version"] = latest
                result["release_notes"] = "（经备用通道检查，更新内容详见发布页）"
                if self._compare_versions(latest, self.current_version) > 0:
                    result["has_update"] = True
            except Exception:
                result["error"] = str(api_err)
                print(f"[Updater] 检查更新失败: {api_err}")

        return result

    def _latest_tag_via_redirect(self) -> str:
        """通过 github.com/{repo}/releases/latest 的 302 Location 解析最新 tag

        GitHub 会把该 URL 重定向到 /releases/tag/vX.Y.Z，无需 API 配额。
        """
        req = urllib.request.Request(
            f"https://github.com/{self.repo}/releases/latest",
            headers={"User-Agent": "LiveCompanion-Updater/1.0"},
        )

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=10):
                # 没有 302 说明仓库没有 release，视为无法解析
                raise ValueError("releases/latest 未发生重定向（仓库可能没有发布版本）")
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
            location = e.headers.get("Location", "")
        tag = location.rstrip("/").rsplit("/", 1)[-1].removeprefix("v")
        if not tag or not tag[0].isdigit():
            raise ValueError(f"无法从重定向解析版本号: {location}")
        return tag

    def download_installer(self, url: str, progress_callback=None) -> str:
        """下载installer到临时目录

        Args:
            url: 下载地址
            progress_callback: 回调 (downloaded_bytes, total_bytes) -> None

        Returns:
            下载后的本地文件路径，失败返回空字符串
        """
        try:
            tmp_dir = Path(os.environ.get("TEMP", str(Path.home())))
            installer_path = tmp_dir / "旁白_Setup.exe"

            req = urllib.request.Request(url, headers={"User-Agent": "LiveCompanion-Updater/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536

                with open(installer_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)

            print(f"[Updater] installer下载完成: {installer_path}")
            return str(installer_path)

        except Exception as e:
            print(f"[Updater] 下载失败: {e}")
            return ""

    def install_and_restart(self, installer_path: str):
        """退出当前程序，运行installer静默安装，安装后重启程序

        Args:
            installer_path: installer.exe的本地路径
        """
        try:
            # 创建重启脚本：等待当前进程退出后运行installer，安装完成后再启动新程序
            exe_path = sys.executable if getattr(sys, 'frozen', False) else ""
            script_path = Path(os.environ.get("TEMP", str(Path.home()))) / "live_companion_update.bat"

            if exe_path:
                # exe模式：静默安装后重启程序
                script = f"""@echo off
timeout /t 2 /nobreak >nul
start "" "{installer_path}" /SILENT /NORESTART
timeout /t 15 /nobreak >nul
start "" "{exe_path}"
del "%~f0"
"""
            else:
                # 脚本模式：只运行installer
                script = f"""@echo off
timeout /t 2 /nobreak >nul
start "" "{installer_path}" /SILENT /NORESTART
del "%~f0"
"""

            with open(script_path, "w", encoding="gbk") as f:
                f.write(script)

            # 用CREATE_NO_WINDOW启动更新脚本，不阻塞当前退出
            subprocess.Popen(
                ["cmd", "/c", str(script_path)],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # 退出当前程序
            print("[Updater] 正在退出以进行升级...")
            os._exit(0)

        except Exception as e:
            print(f"[Updater] 启动安装失败: {e}")

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """比较两个语义化版本号

        Returns:
            1 if v1 > v2, -1 if v1 < v2, 0 if equal
        """
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            # 补齐长度
            while len(parts1) < len(parts2):
                parts1.append(0)
            while len(parts2) < len(parts1):
                parts2.append(0)
            for a, b in zip(parts1, parts2):
                if a > b:
                    return 1
                if a < b:
                    return -1
            return 0
        except Exception:
            return 0
