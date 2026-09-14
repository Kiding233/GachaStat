"""资源生命周期：限时货币到期转换/清零（P77）。

仅承载原始规则与时间解析：ResourceLifecycle / ResourceLifecycleConfig +
resolve_expire_time()。策略可读预览类型 ResourceExpiryPreview 定义在
core/strategy.py（与 StrategyContext 同处策略域），由
strategy_context_builder 负责把原始规则转为预览，避免策略核心对资源
配置层的反向依赖（P58/P61 先例）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ResourceLifecycle:
    """限时资源生命周期：到期时刻 + 到期行为。"""

    resource_id: str  # 作用对象（如 "tof_token_a"）
    expire_at: Optional[float] = None  # 绝对到期时间（秒）。与 expire_with_banner 互斥
    expire_with_banner: Optional[str] = None  # 快捷：对齐该 banner 的 available_until（秒）
    on_expire: Optional[dict] = None  # 转换 {convert_to, from, to} | 清零 {clear} | None 无生命周期声明


@dataclass
class ResourceLifecycleConfig:
    enabled: bool = True
    rules: List[ResourceLifecycle] = field(default_factory=list)


def resolve_expire_time(
    rule: ResourceLifecycle,
    banner_dict: Dict[str, Optional[float]],
) -> Optional[float]:
    """解析单条规则的到期时刻（秒）。

    Args:
        rule: 资源生命周期规则。
        banner_dict: banner_id → available_until（秒）映射，用于
            expire_with_banner 快捷展开。缺失或 available_until 为 None 时
            返回 None（校验层负责报错，这里只做解析回退）。

    Returns:
        到期时刻（秒），无法解析时返回 None。
    """
    if rule.expire_at is not None:
        return float(rule.expire_at)
    if rule.expire_with_banner:
        return banner_dict.get(rule.expire_with_banner)
    return None
