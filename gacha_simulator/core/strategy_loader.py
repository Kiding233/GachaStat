"""插件策略扫描与加载器。

扫描 strategies/*.py → importlib 动态加载 → @register_strategy 装饰器自动注册。
加载失败的插件注册为 _invalid_state 占位 meta。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def load_plugin_strategies(plugin_dir: Optional[str] = None) -> int:
    """扫描插件目录中的所有 .py 文件并通过 importlib 加载。

    每个 .py 文件作为独立模块导入——文件中的 @register_strategy 装饰器
    副作用会自动将策略注册到 STRATEGY_REGISTRY。

    Args:
        plugin_dir: 插件目录路径。None 时从 paths.get_strategies_dir() 获取。

    Returns:
        成功加载的插件数量。

    Raises:
        无——加载失败的插件注册为 _invalid_state 占位，不会阻止应用启动。
    """
    if plugin_dir is None:
        from ..paths import get_strategies_dir
        plugin_dir = get_strategies_dir()

    if not os.path.isdir(plugin_dir):
        logger.debug("插件目录不存在，跳过扫描: %s", plugin_dir)
        return 0

    # 延迟导入——避免循环依赖（strategy.py 可能尚未完全初始化）
    from .strategy import STRATEGY_REGISTRY

    loaded_count = 0
    for filename in sorted(os.listdir(plugin_dir)):
        if not filename.endswith('.py') or filename.startswith('_'):
            continue

        module_name = filename[:-3]  # 去掉 .py
        plugin_key = f"plugin/{module_name}"
        filepath = os.path.join(plugin_dir, filename)

        try:
            spec = importlib.util.spec_from_file_location(
                f"gacha_simulator_strategy_plugin_{module_name}",
                filepath,
            )
            if spec is None or spec.loader is None:
                _register_failed(
                    plugin_key, module_name, filepath,
                    "无法创建模块规格（spec_from_file_location 返回 None）"
                )
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # 校验 key 前缀——插件必须以 plugin/ 开头
            meta = STRATEGY_REGISTRY.get(plugin_key)
            if meta is None:
                # 插件文件中的 @register_strategy 使用了非 plugin/ 前缀的 key
                _register_failed(
                    plugin_key, module_name, filepath,
                    f"插件 key 必须以 'plugin/' 开头，"
                    f"但 @register_strategy 未使用 '{plugin_key}'"
                )
                continue

            loaded_count += 1
            logger.info("插件加载成功: %s (%s)", plugin_key, filepath)

        except Exception as exc:
            _register_failed(
                plugin_key, module_name, filepath,
                f"{type(exc).__name__}: {exc}"
            )

    logger.info("插件扫描完成: %d 个成功", loaded_count)
    return loaded_count


def _register_failed(
    plugin_key: str,
    module_name: str,
    filepath: str,
    error_msg: str,
) -> None:
    """注册加载失败的插件占位 meta。"""
    from .strategy import STRATEGY_REGISTRY, StrategyMeta

    logger.warning("插件加载失败: %s —— %s", filepath, error_msg)

    STRATEGY_REGISTRY[plugin_key] = StrategyMeta(
        key=plugin_key,
        display_name=f"plugin/{module_name}",
        description=f"加载失败: {error_msg}",
        cls=None,
        params=[],
        internal=False,
        disabled=False,
        plugin_path=filepath,
        _invalid_state=error_msg,
    )


def reload_plugin_strategy(name: str) -> bool:
    """重新加载单个插件模块。

    Args:
        name: 插件 key（如 'plugin/my_adaptive'）或模块名（如 'my_adaptive'）。

    Returns:
        重新加载成功返回 True。
    """
    from ..paths import get_strategies_dir
    from .strategy import STRATEGY_REGISTRY

    plugin_dir = get_strategies_dir()
    module_name = name.replace('plugin/', '') if name.startswith('plugin/') else name
    filepath = os.path.join(plugin_dir, f"{module_name}.py")

    if not os.path.isfile(filepath):
        logger.error("插件文件不存在: %s", filepath)
        return False

    plugin_key = f"plugin/{module_name}"

    try:
        spec = importlib.util.spec_from_file_location(
            f"gacha_simulator_strategy_plugin_{module_name}",
            filepath,
        )
        if spec is None or spec.loader is None:
            logger.error("无法创建模块规格: %s", filepath)
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # 清除旧的 _invalid_state
        meta = STRATEGY_REGISTRY.get(plugin_key)
        if meta is not None:
            meta._invalid_state = None

        logger.info("插件重新加载成功: %s", plugin_key)
        return True

    except Exception as exc:
        logger.error("插件重新加载失败: %s —— %s: %s", plugin_key, type(exc).__name__, exc)
        return False


def disable_plugin_strategy(name: str) -> bool:
    """禁用插件策略（设置 StrategyMeta.disabled = True）。

    Args:
        name: 插件 key（如 'plugin/my_adaptive'）。

    Returns:
        操作成功返回 True。key 不存在或非插件策略返回 False。
    """
    from .strategy import STRATEGY_REGISTRY

    meta = STRATEGY_REGISTRY.get(name)
    if meta is None:
        logger.warning("disable_plugin_strategy: key 不存在: %s", name)
        return False
    if meta.internal:
        logger.warning("disable_plugin_strategy: 不能禁用 internal 策略: %s", name)
        return False

    meta.disabled = True
    logger.info("插件已禁用: %s", name)
    return True


def enable_plugin_strategy(name: str) -> bool:
    """启用插件策略（设置 StrategyMeta.disabled = False）。

    Args:
        name: 插件 key（如 'plugin/my_adaptive'）。

    Returns:
        操作成功返回 True。key 不存在或非插件策略返回 False。
    """
    from .strategy import STRATEGY_REGISTRY

    meta = STRATEGY_REGISTRY.get(name)
    if meta is None:
        logger.warning("enable_plugin_strategy: key 不存在: %s", name)
        return False

    meta.disabled = False
    logger.info("插件已启用: %s", name)
    return True
