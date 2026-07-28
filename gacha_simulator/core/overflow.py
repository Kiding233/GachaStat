"""P63：溢出卡资源转换——分段表数据结构与匹配逻辑。

统一模型：CardAcquired 触发点的溢出规则 = 分段表（互斥完备区间 → 产出）。
三字段语法糖（first_time_bonus / nth_time_bonus / excess_bonus）在此展开为 bands，
应用层只看到分段表。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class OverflowBand:
    """分段表的一个区间——min 到 max（含两端），命中时产出 resources。

    max=None 表示无穷大（∞）——该区间覆盖 [min, +∞)。
    TOML 中写 "inf" 字符串，解析时转为 None。
    """
    min: int
    max: Optional[int]  # None = ∞
    resources: Dict[str, float] = field(default_factory=dict)


def match_overflow_bands(
    bands: List[OverflowBand],
    n: int,
) -> Dict[str, float]:
    """根据 total_holding=n 定位分段表区间，返回命中区间的产出。

    Args:
        bands: 分段表列表（区间互斥，顺序无关——内部会排序）。
        n: 获得后的累计持有次数（total_holding），≥1。

    Returns:
        命中区间的 resources dict；若 n 落在所有区间之外（间隙）则返回 {}。

    Examples:
        >>> b = OverflowBand(1, None, {"gem": 40})
        >>> match_overflow_bands([b], 1)
        {'gem': 40}
        >>> match_overflow_bands([b], 100)
        {'gem': 40}
        >>> b2 = OverflowBand(1, 1, {"A": 10})
        >>> match_overflow_bands([b2], 2)  # 间隙
        {}
    """
    if not bands:
        return {}

    for band in bands:
        if band.min <= n:
            if band.max is None or n <= band.max:
                return dict(band.resources)

    return {}


def expand_sugar_to_bands(
    first_time_bonus: Optional[Dict[str, float]] = None,
    nth_time_bonus: Optional[Dict[int, Dict[str, float]]] = None,
    excess_bonus: Optional[Dict] = None,
) -> List[OverflowBand]:
    """将三字段语法糖展开为分段表（OverflowBand 列表）。

    展开规则：
      first_time_bonus = {X: 10}       → [1, 1] → {X: 10}
      nth_time_bonus = {3: {X: 20}}    → [3, 3] → {X: 20}
      excess_bonus = {threshold: 7, resources: {X: 25}}  → [7, ∞) → {X: 25}

    三字段可自由组合。区间互斥且不重叠（first=1, nth≥2, excess≥threshold）。
    相邻同产出区间不在此合并——由独立函数处理（若需要）。

    Args:
        first_time_bonus: 首次获得产出。
        nth_time_bonus: 第 N 次获得产出映射。
        excess_bonus: 满突后产出——含 threshold 和 resources 键。

    Returns:
        OverflowBand 列表，按 min 升序排列。
    """
    bands: List[OverflowBand] = []

    # 首次获得：[1, 1]
    if first_time_bonus:
        bands.append(OverflowBand(min=1, max=1, resources=dict(first_time_bonus)))

    # 第 N 次获得：每个 N → [N, N]
    if nth_time_bonus:
        for n_val, resources in sorted(nth_time_bonus.items()):
            bands.append(OverflowBand(min=n_val, max=n_val, resources=dict(resources)))

    # 满突后：[threshold, ∞)
    if excess_bonus:
        threshold = excess_bonus.get('threshold', 999999)
        resources = excess_bonus.get('resources', {})
        if resources:
            bands.append(OverflowBand(min=threshold, max=None, resources=dict(resources)))

    # 按 min 升序排列
    bands.sort(key=lambda b: b.min)
    return bands
