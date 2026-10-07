"""用 playwright 加载 layout_demo 的静态页：截图 + DOM 断言。

这些页面是纯静态 HTML（Vue/Element Plus 走 CDN），改完必须看渲染结果，
否则会出现「15 个自闭合标签导致整页空白」那类静默失败。

用法：
    python shot.py <页面.html> <输出.png> [页面名] [--js "先执行的 JS"]

「页面名」用于选择断言组：index / tabs / carbon，省略则用通用断言。
--js 用来切状态（如点第 5 个配置标签）后再截图。

用系统已装的 Chrome（channel="chrome"），不额外下载 chromium。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent

# 通用断言：抓最常见的静默失败（面板空白、层级穿帮、内容落错页）
COMMON = """
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0; };
  const rowsOf = sel => { const m = {}; document.querySelectorAll(sel).forEach(t => {
    const y = Math.round(t.getBoundingClientRect().top); m[y] = (m[y]||0)+1; }); return m; };
  const txt = document.body.innerText || '';
  return {
    bodyText: txt.length,
    // Vue 未挂载或 v-cloak 未摘时会露出来
    cloaked: document.querySelectorAll('[v-cloak]').length,
    unrendered: (txt.match(/\\{\\{/g) || []).length,
    visibleSections: [...document.querySelectorAll('.cfg-pane,.an-pane,.pane')].filter(vis).length,
  };
})()
"""

# 探针页专有：标签行是否单行、内容区是否恰好一个、嵌入件是否落在自己那页
INDEX = """
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0; };
  const rowsOf = sel => { const m = {}; document.querySelectorAll(sel).forEach(t => {
    const y = Math.round(t.getBoundingClientRect().top); m[y] = (m[y]||0)+1; }); return m; };
  return {
    cfgTabs: document.querySelectorAll('.cfg-tab').length,
    cfgRows: rowsOf('.cfg-tab'),
    cfgPaneVisible: [...document.querySelectorAll('.cfg-pane')].filter(vis).length,
    anTabs: document.querySelectorAll('.an-tab').length,
    anRows: rowsOf('.an-tab'),
    anPaneVisible: [...document.querySelectorAll('.an-pane')].filter(vis).length,
    anLabels: [...document.querySelectorAll('.an-tab')].map(t => t.innerText.trim()),
    embeds: [...document.querySelectorAll('.embed')].map(e => ({
      vis: vis(e), w: Math.round(e.getBoundingClientRect().width),
      h: Math.round(e.getBoundingClientRect().height),
      title: (e.querySelector('.embed-h b') || {}).textContent || '' })),
    sub2: [...document.querySelectorAll('.sub2 button')].map(b => b.innerText.trim()),
    sub2Visible: vis(document.querySelector('.sub2')),
    bodyText: (document.body.innerText || '').length,
    unrendered: ((document.body.innerText || '').match(/\\{\\{/g) || []).length,
  };
})()
"""

# 对照页专有：有多少个变体区块、二级候选是否齐备
TABS = """
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0; };
  return {
    sections: document.querySelectorAll('section.v').length,
    s2rows: document.querySelectorAll('.s2row').length,
    s2labels: [...document.querySelectorAll('.s2lab b')].map(b => b.innerText.trim()),
    d1tabs: document.querySelectorAll('.d1tab').length,
    subButtons: [...document.querySelectorAll('.sub')].map(s =>
      [...s.querySelectorAll('button')].map(b => b.innerText.trim())),
    bodyText: (document.body.innerText || '').length,
    unrendered: ((document.body.innerText || '').match(/\\{\\{/g) || []).length,
  };
})()
"""

PROBES = {"index": INDEX, "tabs": TABS, "common": COMMON}


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit(__doc__)
    page = Path(args[0])
    if not page.is_absolute():
        page = (Path.cwd() / page).resolve()
    out = Path(args[1])
    probe_name = "common"
    pre_js = ""
    rest = [a for a in args[2:] if not a.startswith("--")]
    if rest:
        probe_name = rest[0]
    if "--js" in args:
        pre_js = args[args.index("--js") + 1]

    probe = PROBES.get(probe_name, COMMON)

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1520, "height": 950}, device_scale_factor=1)
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}")
              if m.type == "error" else None)
        pg.goto(page.as_uri())
        pg.wait_for_timeout(2500)
        if pre_js:
            pg.evaluate(pre_js)
            pg.wait_for_timeout(900)
        pg.screenshot(path=str(out), full_page="--full" in args)
        result = pg.evaluate(probe)
        b.close()

    if errs:
        print("ERRORS", json.dumps(errs[:8], ensure_ascii=False))
    print("PROBE", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
