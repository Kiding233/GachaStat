"""GachaStat Web 视图层（P74 换头计划阶段 1b/2）——pywebview js_api 桥。

与 gui/（PyQt6 旧 UI）平行的新 UI 后端：不依赖 Qt，直接复用 core/service 引擎。
新 UI 前端（Vue3）经 window.pywebview.api 调用本包的 GachaApi 方法。

架构：
- GachaApi（api.py）：js_api 桥类，前端可调用的全部方法
- 异步模拟：js_api 方法启动后台线程，evaluate_js 推送进度/完成（已验证线程安全）
- 数据集：复用 core/result_store.py 的 StoredDataset（全 JSON 可序列化）

运行：python -m gacha_simulator.main_webview  （与 python -m gacha_simulator.main 平行）
"""
