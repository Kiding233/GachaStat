// ══════════════════════════════════════════════════════════════════
// 图表滚轮统一处理：capture 阶段拦截，防止 ECharts(zrender) 锁死页面滚动
//
// 根因：ECharts 的 dataZoom/inside（RoamController）对 wheel 事件在
// `_checkTriggerMoveZoom` 里无条件 `eventTool.stop`（preventDefault +
// stopPropagation），且 mergeControllerParams 硬编码 `zoomOnMouseWheel: true`。
// 因此只要图表挂了 inside dataZoom，鼠标在图上滚轮时页面/结果区滚动就被
// 无条件阻止——既不能缩放，也不能上下滚动（option 层的 zoomOnMouseWheel
// 设 false/'ctrl' 都无法阻止这层 stop，因为 RoamController 在回调前已 stop）。
//
// 解法：在图表容器上用 capture 阶段监听 wheel，先于 zrender 的 canvas
// listener 收到事件并 stopPropagation，使事件根本不传播到 zrender——
// 这样 zrender 的 eventTool.stop 永不执行。行为对齐旧 UI wheel_blocker：
//   Ctrl+滚轮 → dispatchAction dataZoom 缩放（±比例）
//   普通滚轮  → 不 preventDefault → 放行给页面/结果区滚动
// ══════════════════════════════════════════════════════════════════

// 已绑定容器集（WeakSet：同一 el 重复 init/绑定不叠加监听，防双缩放）
const _bound = new WeakSet()

export function bindZoomWheel(el, inst) {
  if (!el || _bound.has(el)) return
  const onWheel = (e) => {
    // 先于 zrender 拦下事件。zrender 的 wheel 监听绑在同一容器 el 的 bubble 阶段，
    // 而本监听器注册在 capture 阶段（先执行）。必须用 stopImmediatePropagation：
    // stopPropagation 只能阻止传播到父节点，无法阻止同一 target 上后续监听器。
    // 阻断事件到达 zrender → 其 eventTool.stop（preventDefault）永不执行 → 页面滚动不被锁死。
    e.stopImmediatePropagation()
    // 非 Ctrl：不 preventDefault，浏览器默认滚动照常（目标=最近可滚动祖先，结果区 right-col）
    if (!e.ctrlKey || !inst) return
    e.preventDefault()
    let opt
    try { opt = inst.getOption() } catch (err) { return }
    const dz = (opt.dataZoom && opt.dataZoom[0]) || { start: 0, end: 100 }
    const start = dz.start ?? 0
    const end = dz.end ?? 100
    const span = end - start
    const factor = e.deltaY > 0 ? 0.85 : 1.18
    const newSpan = Math.max(8, Math.min(100, span * factor))
    const center = (start + end) / 2
    inst.dispatchAction({ type: 'dataZoom', start: Math.max(0, center - newSpan / 2), end: Math.min(100, center + newSpan / 2) })
  }
  el.addEventListener('wheel', onWheel, { capture: true, passive: false })
  _bound.add(el)
  return () => { el.removeEventListener('wheel', onWheel, { capture: true }); _bound.delete(el) }
}
