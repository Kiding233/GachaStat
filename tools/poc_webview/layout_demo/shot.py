"""用 playwright 加载 layout_demo 的静态页：截图 + DOM 断言。

这些页面是纯静态 HTML（Vue/Element Plus 走 CDN），改完必须看渲染结果，
否则会出现「15 个自闭合标签导致整页空白」那类静默失败。

用法：
    python shot.py <页面.html> <输出.png> [页面名] [--js "先执行的 JS"] [--full] [--at 0,3,5]

「页面名」用于选择断言组：index / tabs / chart，省略则用通用断言。
--js 用来切状态（如点第 5 个配置标签）后再截图。
--at 把第 N 个 .gs-chart 滚到视口顶部各截一张（长页整页截图会缩到看不清字）。

用系统已装的 Chrome（channel="chrome"），不额外下载 chromium。
"""
from __future__ import annotations

import json
import sys
import time
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
    // 每个专题必须恰有一个主方法（●）。多一个或少一个都是标 main 时漏改，
    // 而这种错在界面上只表现为「两个点都是实心」，不看不出来。
    badMain: [...document.querySelectorAll('.an-pane')].map(p => ({
      cat: (p.querySelector('.an-side-h span') || {}).textContent?.trim() || '(占位)',
      items: p.querySelectorAll('.an-it').length,
      mains: p.querySelectorAll('.an-it.main').length,
    })).filter(x => x.items > 0 && x.mains !== 1),
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

# 图表页专有：每个 .gs-chart 是否真的挂上了 ECharts（出了 svg/canvas），
# 以及渲染器选择、空图、控制台报错。图表挂不上时页面看起来只是「图没了」，
# 静态截图不会告诉你原因，所以这里必须断言。
CHART = """
(() => {
  const vis = e => { if (!e) return false; const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0; };
  const boxes = [...document.querySelectorAll('.gs-chart')];
  const empty = boxes.filter(b => !b.querySelector('svg,canvas'));
  const zero = boxes.filter(b => { const r = b.getBoundingClientRect();
    return r.width === 0 || r.height === 0; });
  return {
    boxes: boxes.length,
    mounted: boxes.length - empty.length,
    empty: empty.length,
    zeroSize: zero.length,
    renderers: boxes.map(b => b.querySelector('canvas') ? 'canvas'
      : (b.querySelector('svg') ? 'svg' : '-')),
    svgText: document.querySelectorAll('.gs-chart svg text').length,
    gsStats: (window.GS && GS._stats) ? GS._stats() : null,
    bodyText: (document.body.innerText || '').length,
    unrendered: ((document.body.innerText || '').match(/\\{\\{/g) || []).length,
    cloaked: document.querySelectorAll('[v-cloak]').length,
    depfail: (() => { const e = document.getElementById('depfail');
      return !!e && vis(e); })(),
  };
})()
"""

PROBES = {"index": INDEX, "tabs": TABS, "chart": CHART, "common": COMMON}


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit(__doc__)
    page = Path(args[0])
    if not page.is_absolute():
        page = (Path.cwd() / page).resolve()
    out = Path(args[1])
    # 所有带值的选项先摘掉，剩下的裸参数才是页面名；否则 --at 的值会被当成页面名
    VALUE_FLAGS = {"--js", "--at"}
    bare, skip = [], False
    for a in args[2:]:
        if skip:
            skip = False
            continue
        if a in VALUE_FLAGS:
            skip = True
            continue
        if a.startswith("--"):
            continue
        bare.append(a)
    probe_name = bare[0] if bare else "common"
    pre_js = args[args.index("--js") + 1] if "--js" in args else ""
    at = ([int(x) for x in args[args.index("--at") + 1].split(",") if x.strip()]
          if "--at" in args else [])

    probe = PROBES.get(probe_name, COMMON)

    last = None
    for attempt in range(3):
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome")
            pg = b.new_page(viewport={"width": 1520, "height": 950}, device_scale_factor=1)
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
            pg.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}")
                  if m.type == "error" else None)
            # 一律屏蔽外部请求：这些页面必须能离线渲染。
            # 出过一次真事故：页面从 CDN 取 Vue，CDN 一抖动整个应用退化成裸模板
            # （工具栏显示 {{ ... }}、文件树一个节点都没有），而当时的验证在联网下跑，
            # 完全看不出来。依赖现在本地化了，这里把「不许联网」变成硬约束。
            pg.route(
                "**/*",
                lambda r: r.continue_()
                if r.request.url.startswith("file://")
                else r.abort(),
            )
            pg.goto(page.as_uri())
            pg.wait_for_timeout(2500)
            if pre_js:
                pg.evaluate(pre_js)
                pg.wait_for_timeout(900)
            result = pg.evaluate(probe)
            # 模板未渲染 = Vue 没挂上（CDN 抖动或自闭合标签吃掉子树）。
            # 这种坏帧必须重试，且最终一定要报出来，不能拍张图就过。
            broken = result.get("unrendered", 0) > 0 or result.get("cloaked", 0) > 0
            if not broken or attempt == 2:
                pg.screenshot(path=str(out), full_page="--full" in args)
                for n in at:
                    pg.evaluate(
                        """(i) => { const els = document.querySelectorAll('.gs-chart');
                           if (els[i]) els[i].scrollIntoView({block:'start'});
                           window.scrollBy(0, -70); }""", n)
                    pg.wait_for_timeout(500)
                    stem = out.with_suffix("")
                    pg.screenshot(path=f"{stem}-{n}{out.suffix}")
            b.close()
        last = (result, errs, broken)
        if not broken:
            break
        print(f"RETRY {attempt + 1}/3：模板未渲染（{{{{ }}}} 残留 "
              f"{result.get('unrendered')} 处），重载")
        time.sleep(1.5)

    result, errs, broken = last
    if errs:
        print("ERRORS", json.dumps(errs[:8], ensure_ascii=False))
    print("PROBE", json.dumps(result, ensure_ascii=False))
    if broken:
        print("FAIL 模板未渲染。该截图不可作为渲染证据")
        raise SystemExit(1)
    print("OK 渲染通过")


if __name__ == "__main__":
    main()
