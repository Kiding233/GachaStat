// ══════════════════════════════════════════════════════════════════
// js_api 桥封装（pywebview）——前端唯一后端入口
//
// 生产：window.pywebview.api.<method>(...)（pywebview 主进程 GachaApi）
// 开发（纯浏览器 npm run dev 独立运行）：devMock 假实现，保证可预览
//
// 任务事件：后端后台线程经 evaluate_js 推送 __gscTaskProgress / __gscTaskDone，
// 此模块统一监听并分发给注册的回调（模拟/搜索任务的进度与完成）。
// ══════════════════════════════════════════════════════════════════

// ⚠ bridge 必须调用时动态检测（不能模块加载时快照）：pywebview 注入
// window.pywebview 晚于 Vue mount，模块加载时快照会拿到 null 而误走 devMock。
function currentBridge() {
  return typeof window !== 'undefined' ? window.pywebview?.api : null
}
export const hasBridge = typeof window !== 'undefined' && !!window.pywebview?.api

async function call(method, ...args) {
  const b = currentBridge()
  if (b && typeof b[method] === 'function') {
    return b[method](...args)
  }
  if (devMock[method]) return devMock[method](...args)
  return { ok: false, error: `后端方法不存在: ${method}（生产需经 pywebview 运行）` }
}

// ── 任务事件监听（__gscTaskProgress / __gscTaskDone）──
const progressHandlers = []
const doneHandlers = []
export function onTaskProgress(fn) { progressHandlers.push(fn) }
export function onTaskDone(fn) { doneHandlers.push(fn) }

if (typeof window !== 'undefined') {
  window.__gscTaskProgress = (p) => { progressHandlers.forEach((fn) => fn(p)) }
  window.__gscTaskDone = (p) => { doneHandlers.forEach((fn) => fn(p)) }
}

// ── 接口（与 GachaApi 方法一一对应）──
export const api = {
  // 配置
  loadConfigText: () => call('load_config_text'),
  saveConfigText: (text) => call('save_config_text', text),
  resetDefaultConfig: () => call('reset_default_config'),
  importConfigFile: (path) => call('import_config_file', path),
  exportConfigFile: (path) => call('export_config_file', path),
  getConfigPath: () => call('get_config_path'),
  getConfigMeta: () => call('get_config_meta'),
  listGdrOptions: () => call('list_gdr_options'),
  listStrategyOptions: () => call('list_strategy_options'),

  // 模拟任务（异步）
  startSimulation: (configText, params) => call('start_simulation', configText, params),
  getTaskStatus: (taskId) => call('get_task_status', taskId),
  getTaskResult: (taskId) => call('get_task_result', taskId),

  // 数据集
  registerDataset: (dataset) => call('register_dataset', dataset),
  saveDataset: (dataset, name) => call('save_dataset', dataset, name),
  loadDataset: (name) => call('load_dataset', name),
  deleteDataset: (name) => call('delete_dataset', name),
  listDatasets: () => call('list_datasets'),

  // 分析（同步，返回 sections）
  runAnalysis: (datasetId, method, params) => call('run_analysis', datasetId, method, params),
  runProcessAnalysis: (datasetId, params) => call('run_process_analysis', datasetId, params),
  runVulnerability: (datasetId, params) => call('run_vulnerability', datasetId, params),
  generateRetreatConfig: (params) => call('generate_retreat_config', params),
  generateWorstConfig: (datasetId, params) => call('generate_worst_config', datasetId, params),
  analyzeWorstDist: (datasetId, params) => call('analyze_worst_dist', datasetId, params),
  runComparison: (datasetIds, params) => call('run_comparison', datasetIds, params),
  startPlanSearch: (configText, params) => call('start_plan_search', configText, params),

  // 资源监控 / 关于 / 插件
  getResourceUsage: () => call('get_resource_usage'),
  getAboutInfo: () => call('get_about_info'),
  listPlugins: () => call('list_plugins'),
  togglePlugin: (key, disable) => call('toggle_plugin', key, disable),
}

// 文件对话框（pywebview 原生，Python 侧 create_file_dialog）
export function pickFile(save = false, fileTypes = ['所有文件 (*)']) {
  return call('pick_file', save, fileTypes)
}

// ── 开发 Mock（无 pywebview 时浏览器独立预览用）──────────────────
const devMock = {
  load_config_text: () => ({ ok: true, text: '' }),
  get_config_meta: () => ({ ok: true, banners: [], targets: [], initial_resources: {}, strategy_key: 'smart' }),
  list_gdr_options: () => ({ ok: true, options: [] }),
  list_strategy_options: () => ({ ok: true, options: [] }),
  start_simulation: () => ({ ok: true, task_id: 'mock' }),
  get_task_status: () => ({ ok: true, status: 'done', progress: 100 }),
  get_task_result: () => ({ ok: true, status: 'done', type: 'sim', dataset: null }),
  register_dataset: () => ({ ok: true, dataset_id: 'mock' }),
  save_dataset: () => ({ ok: true }),
  load_dataset: () => ({ ok: false, error: 'no bridge' }),
  list_datasets: () => ({ ok: true, datasets: [] }),
  run_analysis: () => ({ ok: false, error: 'no bridge', sections: [] }),
  run_process_analysis: () => ({ ok: false, error: 'no bridge', sections: [] }),
  run_vulnerability: () => ({ ok: false, error: 'no bridge', sections: [] }),
  generate_retreat_config: () => ({ ok: false, error: 'no bridge' }),
  generate_worst_config: () => ({ ok: false, error: 'no bridge' }),
  analyze_worst_dist: () => ({ ok: false, error: 'no bridge', sections: [] }),
  run_comparison: () => ({ ok: false, error: 'no bridge', sections: [] }),
  start_plan_search: () => ({ ok: true, task_id: 'mock' }),
  get_resource_usage: () => ({ ok: true, cpu: null, mem: null }),
  get_about_info: () => ({ ok: true, version: 'dev', name: 'GachaStat', tech: 'dev 模式（无 pywebview）' }),
  list_plugins: () => ({ ok: true, plugins: [] }),
  toggle_plugin: () => ({ ok: true }),
}

export default api
