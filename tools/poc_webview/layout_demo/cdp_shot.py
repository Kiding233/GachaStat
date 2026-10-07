"""用 Chrome 的 CDP 直接驱动加载+截图+DMO 断言。

本机没有 playwright / puppeteer / selenium，但 Chrome 与 websocket-client 都在，
所以走 DevTools 协议。一次性工具，服务于 layout_demo 的三个页面。

用法：
    python cdp_shot.py <page.html> <out.png> [--js "在页面里先执行的 JS"] [--probe probe.js]

--js     用于切换状态（如点第 5 个配置标签）后再截图
--probe  一段返回 JSON 的 JS 表达式，用于断言渲染结果（标签行数、可见 pane 数等）
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import websocket

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Browser:
    """极简 CDP 客户端：够用即可，不做通用抽象。"""

    def __init__(self, width: int, height: int, port: int | None = None):
        binary = _find_browser()
        if not binary:
            raise RuntimeError("找不到 Chrome / Edge")
        # 已有实例（--port 指定）时直接接上去，省去冷启动与沙箱问题
        self._own = port is None
        self._port = port or _free_port()
        self._proc = None if port else subprocess.Popen(
            [
                binary,
                "--headless=new",
                f"--remote-debugging-port={self._port}",
                # Chrome 111+ 对 CDP 的 websocket 做 origin 校验，不放开会 403
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._ws = None
        self._id = 0
        self._pending: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._session = None
        self._ready = threading.Event()
        self._wait_ready()

    def _wait_ready(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = urllib.request.urlopen(
                    f"http://127.0.0.1:{self._port}/json/version", timeout=1
                ).read()
                url = json.loads(raw)["webSocketDebuggerUrl"]
                self._ws = websocket.create_connection(url, timeout=60)
                threading.Thread(target=self._pump, daemon=True).start()
                return
            except Exception:
                time.sleep(0.3)
        raise RuntimeError("CDP 连接不上")

    def _pump(self) -> None:
        while True:
            try:
                msg = json.loads(self._ws.recv())
            except Exception:
                return
            mid = msg.get("id")
            if mid is not None:
                slot = self._pending.get(mid)
                if slot is not None:
                    slot["result"] = msg
                    slot["done"].set()

    def send(self, method: str, params: dict | None = None, session: str | None = None):
        with self._lock:
            self._id += 1
            mid = self._id
            done = threading.Event()
            slot = {"done": done, "result": None}
            self._pending[mid] = slot
        payload = {"id": mid, "method": method, "params": params or {}}
        if session:
            payload["sessionId"] = session
        self._ws.send(json.dumps(payload))
        if not done.wait(60):
            self._pending.pop(mid, None)
            raise TimeoutError(f"{method} 超时")
        self._pending.pop(mid, None)
        return slot["result"]

    def new_page(self, width: int, height: int) -> str:
        t = self.send("Target.createTarget", {"url": "about:blank"})
        tid = t["result"]["targetId"]
        s = self.send("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sid = s["result"]["sessionId"]
        self.send("Page.enable", session=sid)
        self.send("Runtime.enable", session=sid)
        self.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            session=sid,
        )
        self._session = sid
        return sid

    def goto(self, url: str, settle: float = 2.5, session: str | None = None) -> None:
        sid = session or self._session
        self.send("Page.navigate", {"url": url}, session=sid)
        time.sleep(settle)

    def evaluate(self, expr: str, session: str | None = None):
        sid = session or self._session
        r = self.send(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
            session=sid,
        )
        res = r.get("result", {})
        if "exceptionDetails" in res:
            raise RuntimeError(json.dumps(res["exceptionDetails"], ensure_ascii=False))
        return res.get("result", {}).get("value")

    def screenshot(self, out: Path, session: str | None = None) -> None:
        sid = session or self._session
        r = self.send("Page.captureScreenshot", {"format": "png"}, session=sid)
        import base64

        out.write_bytes(base64.b64decode(r["result"]["data"]))

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass
        if self._own and self._proc:
            self._proc.terminate()


PROBE = """
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0; };
  const rowsOf = sel => { const m = {}; document.querySelectorAll(sel).forEach(t => {
    const y = Math.round(t.getBoundingClientRect().top); m[y] = (m[y]||0)+1; }); return m; };
  return {
    cfgTabs: document.querySelectorAll('.cfg-tab').length,
    cfgRows: rowsOf('.cfg-tab'),
    anTabs: document.querySelectorAll('.an-tab').length,
    anRows: rowsOf('.an-tab'),
    anLabels: [...document.querySelectorAll('.an-tab')].map(t => t.innerText.trim()),
    cfgPanesVisible: [...document.querySelectorAll('.cfg-pane')].filter(vis).length,
    anPanesVisible: [...document.querySelectorAll('.an-pane')].filter(vis).length,
    embeds: [...document.querySelectorAll('.embed')].map(e => ({
      vis: vis(e), w: Math.round(e.getBoundingClientRect().width),
      h: Math.round(e.getBoundingClientRect().height),
      title: (e.querySelector('.embed-h b')||{}).textContent || '' })),
    sub2: [...document.querySelectorAll('.sub2 button')].map(b => b.innerText.trim()),
    sub2Visible: vis(document.querySelector('.sub2')),
  };
})()
"""


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit(__doc__)
    page = Path(args[0]).resolve()
    out = Path(args[1]).resolve()
    pre_js = ""
    if "--js" in args:
        pre_js = args[args.index("--js") + 1]
    port = None
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    b = Browser(1520, 950, port=port)
    try:
        b.new_page(1520, 950)
        b.goto(page.as_uri())
        if pre_js:
            b.evaluate(pre_js)
            time.sleep(1.0)
        b.screenshot(out)
        print("PROBE", json.dumps(b.evaluate(PROBE), ensure_ascii=False))
    finally:
        b.close()


if __name__ == "__main__":
    main()
