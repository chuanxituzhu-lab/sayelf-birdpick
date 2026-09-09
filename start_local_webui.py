"""启动本地 WebUI，并在需要时自动拉起 local_server.py。"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8765
PORT_SCAN_LIMIT = 8775


def health(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=0.7
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("ok") and payload.get("localOnly"))
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def choose_port() -> tuple[int, bool]:
    for port in range(DEFAULT_PORT, PORT_SCAN_LIMIT + 1):
        if health(port):
            return port, False
        if not port_in_use(port):
            return port, True
    raise RuntimeError("8765-8775 端口都不可用，请关闭占用端口的程序后重试。")


def start_server(port: int) -> subprocess.Popen[bytes]:
    command = [sys.executable, str(ROOT / "local_server.py"), "--port", str(port)]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 sayelf-birdpick 本地 WebUI")
    parser.add_argument("--port", type=int, help="优先使用的本地端口，默认 8765")
    args = parser.parse_args()

    if args.port is not None:
        port = args.port
        should_start = not health(port)
        if should_start and port_in_use(port):
            raise RuntimeError(f"端口 {port} 已被其他程序占用，且不是 sayelf-birdpick 服务。")
    else:
        port, should_start = choose_port()

    process = None
    if should_start:
        process = start_server(port)
        for _ in range(40):
            if health(port):
                break
            if process.poll() is not None:
                raise RuntimeError("local_server.py 启动失败，请检查 Python 依赖。")
            time.sleep(0.25)
        else:
            process.terminate()
            raise RuntimeError("local_server.py 未在 10 秒内就绪。")

    url = f"http://127.0.0.1:{port}/index.html"
    webbrowser.open(url)
    print(f"sayelf-birdpick WebUI: {url}")
    if should_start:
        print("local_server.py 已在本机后台启动。")
    else:
        print("已复用正在运行的本地识别服务。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        raise SystemExit(1)
