from __future__ import annotations

import argparse
import threading
import time
import webbrowser
import urllib.request

from app.core.model_config import load_env


def _open_browser_when_ready(url: str, health_url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.8)
    # 探活超时仍尝试打开，让用户看到错误页而不是无反馈
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="设计仿真助手 · 前端 + 后端一体化启动")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    load_env()

    base = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
    if not args.no_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(f"{base}/index.html", f"{base}/health"),
            daemon=True,
        ).start()

    import uvicorn

    print(f"正在启动后端与前端: {base}")
    print("（首次启动会拉起 MCP 服务，可能需要 1-2 分钟）")
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
