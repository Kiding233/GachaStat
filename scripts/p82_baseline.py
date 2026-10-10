"""P82 保底管道顺序接线的基线固化与等价对照（P64 §1.5 / §七 P82-2）。

P82 的裁决（2026-09-18）是**接线**：让 `_resolve_order()` 的排序结果成为概率管道
的实际执行顺序。改动落在 `PityEngine.get_behaviors_for_pool()`（P64 §七 P82-1），
而 `PoolPitySpec.pity_names` 保持 TOML 顺序不动——它兼作 `draw_pity_names` 的输出串
来源（`gacha_simulator/core/banner.py` 的 `','.join(pity_spec.pity_names)`），下游
（process_trace / streaming）以 `split(',')` + set 消费，语义与顺序无关，但**字面
顺序会进 golden 快照**。

两个模式：

- **固化**（默认）：
  ``python scripts/p82_baseline.py --config gacha_simulator/config/config.toml --seed 42 --out tests/fixtures/p82_baseline``
  须在**接线前**的代码上运行，把 9 组策略的 `CompactResult` 逐字段固化到快照目录
  （每组策略一个 JSON，形态同 ``tests/fixtures/p79_golden/``）。
- **对照**（``--verify``）：``python scripts/p82_baseline.py --verify``
  在**接线后**的代码上按各快照 meta 记的种子与起始日重跑，逐字段对比。差异必须
  逐一归因到 P64 §1.5 的五类敏感集合（见下方 ``SENSITIVE_CLASSES``），否则视为回归。
  ``draw_pity_names`` 单列一项断言（它承载「输出串不变」这一独立要求）。

**禁止**用 ``scripts/p79_baseline.py`` 覆盖 ``tests/fixtures/p79_golden/``——那是 P79
常驻护栏的基线（P64 §3.4.1.2 已明令）。本脚本的 ``--out`` 默认指向 P82 自己的目录。
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.core.strategy import STRATEGY_REGISTRY  # noqa: E402
from gacha_simulator.core.strategy_loader import load_plugin_strategies  # noqa: E402
from gacha_simulator.service.batch_simulator import (  # noqa: E402
    SimulationEnvBuilder,
    _build_target_set,
    _run_single,
)

# 8 个内置策略 + 已自动加载的插件策略（与 P79 基线同一组，便于两组快照互照）
BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
PLUGIN_KEYS = ['plugin/example_phased']

# 快照的模拟起始日。config.toml 含 monthly_day 收入规则，其日程锚定
# store.sim_start_date，而该字段默认 date.today()——不固定则产物随墙上时钟变化。
# 取 P79 基线的同一个值，使两组快照的时钟条件一致。
SIM_START_DATE = '2026-09-12'

# 不参与对比的字段（时间戳）
SKIP_FIELDS = {'generated_at'}

# P64 §1.5 的五类敏感集合（接线会改变其输出的配置面）。config.toml 仅一条保底定义，
# 五类均不受影响，故对照应得零差异；出现差异即须先归因到本表再判是否为回归。
SENSITIVE_CLASSES = [
    '① 含 rotating_cr 者（掷骰消费全局 random，换序致随机流错位）',
    '② target_featured=True 的 soft 与 hard 共存者（真实概率语义冲突）',
    '③ soft + soft 异 scope（2026-10-06 修正 ① 后由可交换变为不可交换）',
    '④ 跨 type 顺序反转且存在 depends_on 者（依赖方状态键创建时机变化）',
    '⑤ hard 与「在 hard 输出上非恒等」的算子共存（rotating/targeted 的 guaranteed 分支）',
]


def snapshot_name(strategy_key: str) -> str:
    """策略 key → 快照文件名（"/" 转义为 "__"，插件 key 含 "/"）。"""
    return strategy_key.replace('/', '__') + '.json'


def _prepare_env(config: str, sim_start_date: str):
    """加载配置并构造 env + target_set（与 P79 基线同路径）。"""
    store = load_toml(config)
    store.sim_start_date = sim_start_date
    env = SimulationEnvBuilder.from_config_store(store)
    target_specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    # 复用生产构造：_build_target_set 把 card_defs.pools 的全限定键截为 banner 级，
    # 与 _pool_needs_target 的 banner.id 匹配口径恒同；自建 TargetCard 会漏这一步。
    target_set = _build_target_set(env.card_defs, target_specs)
    return env, target_set


def _run_one(env, target_set, strategy_key: str, seed: int):
    """跑一组并返回 (compact, elapsed)。"""
    env.strategy_key = strategy_key
    # 参数取各策略的注册表默认值，不继承配置文件中为其他策略填的参数
    env.strategy_params = {}
    t0 = time.time()
    compact = _run_single(env, target_set, seed, env.initial_resources)
    return compact, time.time() - t0


def generate(config: str, seed: int, out_dir: Path) -> int:
    """固化模式：接线前的代码上跑，写 9 组快照。"""
    n_loaded = load_plugin_strategies()
    print(f'插件加载: {n_loaded} 个')

    keys = BUILTIN_KEYS + PLUGIN_KEYS
    missing = [k for k in keys if k not in STRATEGY_REGISTRY]
    if missing:
        print(f'策略未注册: {missing}', file=sys.stderr)
        return 1

    env, target_set = _prepare_env(config, SIM_START_DATE)
    print(f'config: {config} | pools={len(env.pools)} '
          f'end_time={env.end_time} seed={seed}')
    print(f'目标卡: {len(target_set.targets)} 个')

    out_dir.mkdir(parents=True, exist_ok=True)
    for key in keys:
        compact, elapsed = _run_one(env, target_set, key, seed)
        if compact is None:
            print(f'  {key}: 模拟失败（返回 None）', file=sys.stderr)
            return 1
        payload = {
            'meta': {
                'plan': 'P82',
                'strategy_key': key,
                'config_path': str(config),
                'seed': seed,
                'sim_start_date': SIM_START_DATE,
                'end_time': env.end_time,
                'num_pools': len(env.pools),
                'generated_at': time.time(),
                'wiring': 'pre',
                'note': ('P82 接线前基线（`_resolve_order` 的排序结果尚未接入概率管道）。'
                         '对照口径见 scripts/p82_baseline.py 的 --verify 模式与 P64 §1.5。'),
            },
            'compact': compact.to_dict(),
        }
        (out_dir / snapshot_name(key)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  {key:26s} {elapsed:6.2f}s draws={compact.total_draws:6d} '
              f'waits={compact.total_waits:6d} final_time={compact.final_time:.1f}')

    print(f'已固化 {len(keys)} 组 → {out_dir}')
    return 0


def _diff(old: dict, new: dict) -> list:
    """逐字段差异（跳过 SKIP_FIELDS）。"""
    changed = []
    for k in sorted(set(old) | set(new)):
        if k in SKIP_FIELDS:
            continue
        if old.get(k) != new.get(k):
            changed.append(k)
    return changed


def verify(golden_dir: Path) -> int:
    """对照模式：同种子重跑，逐字段比对快照。"""
    keys = BUILTIN_KEYS + PLUGIN_KEYS
    missing = [k for k in keys if not (golden_dir / snapshot_name(k)).exists()]
    if missing:
        print(f'快照缺失: {missing}', file=sys.stderr)
        return 1

    load_plugin_strategies()
    failures = []
    for key in keys:
        payload = json.loads(
            (golden_dir / snapshot_name(key)).read_text(encoding='utf-8'))
        meta, old = payload['meta'], payload['compact']
        env, target_set = _prepare_env(meta['config_path'], meta['sim_start_date'])
        compact, elapsed = _run_one(env, target_set, key, meta['seed'])
        if compact is None:
            print(f'  FAIL {key:24s} 模拟失败（返回 None）')
            failures.append(key)
            continue
        new = compact.to_dict()
        changed = _diff(old, new)

        # 「draw_pity_names 输出串不变」单列一项断言（P64 §七 P82-2 的独立要求）
        names_changed = old.get('draw_pity_names') != new.get('draw_pity_names')

        if changed or names_changed:
            failures.append(key)
            print(f'  FAIL {key:24s} {elapsed:6.2f}s 差异字段={changed}'
                  + ('；draw_pity_names 变化' if names_changed else ''))
            for k in changed[:6]:
                print(f'         {k}: {str(old.get(k))[:90]} -> {str(new.get(k))[:90]}')
        else:
            print(f'  OK   {key:24s} {elapsed:6.2f}s 逐字段一致；draw_pity_names 不变')

    if failures:
        print(f'\n等价对照结果：FAIL（{len(failures)} 组：{failures}）')
        print('差异须逐一归因到 P64 §1.5 的五类敏感集合，未归因即视为回归：')
        for line in SENSITIVE_CLASSES:
            print(f'  {line}')
        return 1
    print('\n等价对照结果：PASS')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='P82 保底管道顺序接线的基线固化与等价对照')
    parser.add_argument('--config', default='gacha_simulator/config/config.toml')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', default='tests/fixtures/p82_baseline')
    parser.add_argument('--verify', action='store_true',
                        help='对照模式：同种子重跑并逐字段比对快照')
    args = parser.parse_args()

    if args.verify:
        return verify(Path(args.out))
    return generate(args.config, args.seed, Path(args.out))


if __name__ == '__main__':
    sys.exit(main())
