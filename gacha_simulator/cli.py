#!/usr/bin/env python3
"""GachaStat 命令行版本"""

import argparse
import copy
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

sys.path.insert(0, str(Path(__file__).parent))

# **顶层只留轻量导入**（`_version` / `paths`，实测与空解释器同为约 0.03s）。
# 凡触及 `gacha_simulator.core` / `.service` 的导入，一律下沉到各自的函数体内。
# 理由：Windows 用 spawn 起 worker，每个 worker 是全新解释器且**必须重新导入主模块**
# （本文件）才能拿到 `_wk_init` 等 initializer。顶层若有重导入，这笔成本就由每个
# worker 各付一遍：实测 `import gacha_simulator.core` 单次 0.204s，4 个 worker 并发
# 合计 0.57s，占 `pool_start` 的七成（P83 实测 `pool_start` = 0.824s）。
# 下沉后 worker 重导主模块只执行上面两行轻量导入。
# **同型先例**：`core/worst_impact.py:136`、`gui/analysis_panel.py:218`；
# `core/__init__.py` 的 `__getattr__` 惰性导入是同一手法。
from gacha_simulator._version import __version__  # noqa: E402
from gacha_simulator.paths import get_config_dir  # noqa: E402


def _strategy_choices() -> list:
    """`--strategy` 的合法取值：注册表内**非 internal** 的全部键（P83 `1e-3`）。

    只排除 `internal=True`，**不排除禁用项**——生成 choices 时禁用集合尚不可知
    （`[plugins].disabled` 不是 `load_toml` 施加的，且 parser 构造还在 `load_toml`
    之前）。禁用项改由 `_reject_disabled_strategy()` 在 `load_toml` 之后显式拒绝。
    """
    from gacha_simulator.core.strategy import STRATEGY_REGISTRY

    return [key for key, meta in STRATEGY_REGISTRY.items() if not meta.internal]


def _read_disabled_plugins(config_path: Optional[str]) -> list:
    """只读地取本次配置的 `[plugins].disabled`。

    **不调用 `_build_plugins(raw, store)`**：后者会把 `STRATEGY_REGISTRY` 中对应条目
    的 `meta.disabled` 置 `True`（全局注册表副作用），而这条 CLI 进程紧接着就要跑
    模拟，污染注册表会改变 `create_strategy()` 的守卫行为与后续 `--strategy` 语义。
    取法（调用方自行重读文件）与 `gui/main_window.py:232-233` 同型，但**只读比对**。
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib

    path = config_path or os.path.join(get_config_dir(), 'config.toml')
    try:
        with open(path, 'rb') as handle:
            data = tomllib.load(handle)
    except OSError:
        return []
    plugins = data.get('plugins') or {}
    return [str(item) for item in (plugins.get('disabled') or [])]


def _reject_disabled_strategy(strategy: Optional[str], config_path: Optional[str]) -> None:
    """禁用项校验（P83 `1e-3` 第 3 步）。

    **语义差别须写明**：「禁用」从「不作为合法取值被 argparse 接受」降级为「被接受
    后由本步显式拒绝」——生成 choices 时禁用集合尚不可知（parser 构造在 `load_toml`
    之前）。故错误信息由本步给出，并须含被禁用的 key 与 `[plugins].disabled` 出处。
    """
    if not strategy:
        return
    disabled = _read_disabled_plugins(config_path)
    if strategy in disabled:
        print(
            f"错误：策略 {strategy!r} 已在本次配置的 [plugins].disabled 中被禁用，"
            f"不能用于 --strategy。\n"
            f"  出处：{config_path or '默认 config.toml'} 的 [plugins] 段 disabled 列表\n"
            f"  当前禁用项：{disabled}",
            file=sys.stderr,
        )
        sys.exit(2)


def _fallback_target_ids(store) -> list:
    """CLI 无 [[targets]] 时的兜底目标 id（ISSUE-003）。

    展平视图 pool_id 为全限定键 {banner_id}.{pool_id}——直接拼接会生成
    {banner_id}.main_ssr 与真实卡 id 失配、ssr 计数恒 0。取 banner 段拼 _ssr。
    """
    actual = [t.card_id for t in store.target_cards]
    if actual:
        return actual
    if store.pools:
        return [f"{store.pools[0].pool_id.split('.')[0]}_ssr"]
    return []


def _write_perf_json(path, **payload) -> bool:
    """写 P83 的性能载荷。失败只警告不中断（D7：测量失败不得伤及被测对象）。

    载荷字段（§3.5，AUDIT-BREAK-3 **定死五项**）：`stages` / `packet_bytes` /
    `stage_times` / `run_id` / `functions`。后两项是 `cli` 路径 `function` 档闭合链
    的必经环节——适配器进程与被测进程不是同一个，合并结果只能经此回传。

    **2026-09-28 增第六项 `parallel_metrics`**（P83 并行效率增量，L1+L2）：worker 数 /
    每 worker 任务数 / CPU 时间。它同样只在被测进程内可得（进程树是它的），故必须
    经此回传。**新增一项就是改契约**——消费侧（`adapters/cli.py`）须同步，且
    `_perf_json_payload_keys()` 里有断言守着字段集，改一处会被测试拦下。
    """
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        print(f"警告：--perf-json 写入失败（{path}）：{exc}", file=sys.stderr)
        return False


def _merge_profile_functions(profile_dir):
    """在**本进程内**合并本 run 的 cProfile 剖面（P83 §3.8 D3 / AUDIT-BREAK-8②）。

    返回 `(functions, warnings)`：`functions` 为 `[{name, ncalls, tottime, cumtime}, …]`
    或 `None`；`warnings` 为软降级成因（D7）。

    **必须在「运行 run_batch_parallel 的那一个进程」内调用**：`cli` 的 `run_id` 由本
    进程生成，适配器进程既不知道目录名也扫不到它，故合并结果只能经 `--perf-json` 回传。

    **惰性 + 可失败的导入**：`benchmarks/` 是开发侧测量资产、不进发布产物，
    做成模块级硬 import 会让发布产物在 import 期就崩；而剖析只是可选设施，
    缺失时不产剖面即可（§3.8 D7：测量设施不得影响模拟本身）。
    """
    if not profile_dir:
        return None, []
    try:
        from benchmarks.perf.profilers.cprofile import merge_profiles
    except Exception as exc:
        return None, [f'剖析合并设施不可用（benchmarks/ 未随产物分发）：{exc}']
    rows, warnings = merge_profiles(profile_dir)
    if rows is None:
        return None, warnings
    return [
        {'name': name, 'ncalls': ncalls, 'tottime': tottime, 'cumtime': cumtime}
        for name, ncalls, tottime, cumtime in rows
    ], warnings


def main():
    # 重导入下沉至此（理由见文件顶部注释）：worker 不会调用 main()，故不付这笔成本。
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.strategy_loader import load_plugin_strategies
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, run_batch_parallel)

    # P83（1e-3 第 1 步）：**先 load_plugin_strategies()、后构造 parser**。
    # 顺序是硬要求：STRATEGY_REGISTRY 由 @register_strategy 装饰器副作用填充，插件键
    # 只在 load_plugin_strategies 之后才存在，而 argparse 的 choices 在构造时就要求
    # 取值确定。它只依赖 paths.get_strategies_dir()、不依赖配置。
    # 默认路径副作用（如实登记，不得写成「零默认行为变化」）：每次 CLI 启动多一次插件
    # 目录扫描与插件模块导入。插件目录不存在时返回 0 并记 debug 日志，不报错。
    load_plugin_strategies()

    parser = argparse.ArgumentParser(description='GachaStat CLI')
    parser.add_argument('-c', '--config', default=None,
                        help='TOML 配置文件路径（默认：打包 config.toml）')
    parser.add_argument('-n', '--num-simulations', type=int, default=1000,
                        help='Number of simulations')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='Number of parallel workers')
    parser.add_argument('-s', '--seed', type=int, default=42, help='Random seed')
    parser.add_argument('-o', '--output', default='results.json', help='Output file')
    parser.add_argument('--no-pity', action='store_true', help='Disable pity system')
    # P83（1e-3 第 2 步）：choices 由 STRATEGY_REGISTRY 动态生成（只排除 internal）。
    # 原为字面量七键，其中没有 no_draw（它本身已注册，只是没进列表），也不含插件
    # 目录动态注册的键——「不抽卡基线」与「插件策略」两个因子因而无法经产品入口表达。
    parser.add_argument('--strategy', default=None,
        choices=_strategy_choices(),
        help='抽卡策略（默认：使用 config.toml 中指定的策略，回退 smart）。'
             '取值由策略注册表动态生成，含 no_draw 与已加载的插件键')
    parser.add_argument('--strategy-params', default=None,
        help='策略参数，JSON 字符串。例：\'{"desire_weights": {"A": 1.5}, "miss_cost": 0.8}\' '
             '（仅当 --strategy 显式指定时生效；若未指定，使用 config.toml 中的策略参数）')
    parser.add_argument('--output-format', default='simple',
        choices=['simple', 'full'],
        help='输出格式：simple=基础统计JSON, full=含extraction完整数据')
    parser.add_argument('--no-progress', action='store_true',
        help='禁用进度条输出')
    # P83（1e-2）：opt-in 的性能数据通道。**默认全部关闭，关闭时行为与改动前逐项一致**
    # （既不采集也不序列化）。开关用显式参数而非环境变量：可事后从调用点判断本次是否
    # 采集，不引入进程全局隐式状态（同 P83 §3.8 D1 否决环境变量的方向）。
    parser.add_argument('--perf-json', default=None, metavar='PATH',
        help='把阶段计时与三元组序列化字节数写成 JSON（P83 §3.5）。不设置则不采集')
    parser.add_argument('--profile-dir', default=None, metavar='PATH',
        help='开启 cProfile 采样并落到 <PATH>/<run_id>/（P83 §3.8）。不设置则不作任何剖析')
    parser.add_argument('--profile-skip', type=int, default=2, metavar='N',
        help='前 N 次调用不采样（warmup，默认 2）')
    parser.add_argument('--profile-count', type=int, default=50, metavar='K',
        help='每个 worker 各自采样多少次后关闭（默认 50，per-worker 语义）')
    parser.add_argument('--migrate', action='store_true',
        help='检查 TOML 是否为新格式（旧 [[pools]] 格式已不支持自动迁移，见 P61）')
    parser.add_argument('--version', action='version',
        version=f'gacha_simulator {__version__}')

    args = parser.parse_args()

    # P83（1e-2）：阶段计时的采集点之一。`cli.py` 的 `main()` 是两个边界的唯一观察者
    # （配置加载、env 构建）——后四段发生在 run_batch_parallel 函数体内。**只有
    # --perf-json 设置时才取时刻**，默认路径上不引入任何计时调用。
    perf_stages = {}
    # P83 §3.8 D3：run_id 由「运行 run_batch_parallel 的那一个进程」生成。对 cli 路径
    # 而言就是本进程——适配器进程与被测的 `python -m gacha_simulator.cli` 不是同一个
    # 进程，故 run_id 与合并结果只能经 --perf-json 回传（AUDIT-BREAK-3）。
    # **--profile-dir 未设置时 run_id 为 None**（如实标注，不伪造）。
    run_id = uuid.uuid4().hex[:12] if args.profile_dir else None
    _t_config = time.perf_counter() if args.perf_json else 0.0
    if args.config:
        # 用户指定 TOML 路径
        store = load_toml(args.config)
    else:
        # 无参数 → 加载打包默认 config.toml
        default_toml = os.path.join(get_config_dir(), 'config.toml')
        store = load_toml(default_toml)
    if args.perf_json:
        perf_stages['config_load'] = time.perf_counter() - _t_config

    # P83（1e-3 第 3 步）：禁用项在 load_toml 之后校验——生成 choices 时禁用集合尚
    # 不可知（该段不是 load_toml 施加的，且 parser 构造在它之前）。
    _reject_disabled_strategy(args.strategy, args.config)

    # P61（Ph4 / ISSUE-004）：--migrate 依赖已移除的 _build_pools/_migrated_from_legacy
    # （旧 [[pools]] 格式自动迁移随 P61 一次性迁移完成，不再支持）。
    # 空 banner（旧格式残留被解析忽略）→ 显式报错提示手工迁移；非空 → 提示已为新格式。
    if args.migrate:
        if not store.banner.banners:
            print("错误：当前配置不含任何 Banner（旧 [[pools]] 格式已不支持自动迁移）。\n"
                  "请按 P61 迁移规则手工改写为 [[banner]] 格式（见 P61 计划 §3.4 迁移规则）。",
                  file=sys.stderr)
            sys.exit(1)
        else:
            print("TOML 已为新格式，无需迁移。")
            sys.exit(0)

    if args.no_pity:
        store.pity.enabled = False

    # 为 output_data 构造 config 元数据 dict（替代旧 JSON config）
    # P61（ISSUE-325）：num_pools 为跨 Banner 内层池总数（展平视图口径），
    # 补 banner_count 反映 Banner 层数量，CLI 输出语义不静默改变。
    config_meta = {
        'path': str(args.config) if args.config else default_toml,
        'num_pools': len(store.pools),
        'banner_count': len(store.banner.banners),
        'num_cards': len(store.card_defs),
        'pity_enabled': store.pity.enabled,
        'num_targets': len(store.target_cards),
    }

    # 策略覆盖逻辑
    if args.strategy:
        strategy_key = args.strategy  # CLI 参数优先
        if args.strategy_params:
            try:
                strategy_params = json.loads(args.strategy_params)
            except json.JSONDecodeError as e:
                print(f"错误：--strategy-params JSON 解析失败: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            strategy_params = store.strategy_params  # 回退 TOML 配置
    else:
        strategy_key = getattr(store, 'strategy_key', 'smart') or 'smart'
        strategy_params = store.strategy_params

    _t_env = time.perf_counter() if args.perf_json else 0.0
    env = SimulationEnvBuilder.from_config_store(store)
    if args.perf_json:
        perf_stages['env_build'] = time.perf_counter() - _t_env

    # P83 §3.8 D1：`--profile-*` 转成 env 四字段。**注入点是「调用方在拿到 env 之后
    # 直接赋值」，不经 SimulationEnvBuilder 的显式 keyword 表**——from_config_store
    # 与 from_dict 都以显式 keyword 列表构造 env，两张表内均无 profile_*，把字段只
    # 声明在 SimulationEnv 而指望 builder 承载它，结果会是 profile_enabled 恒取默认
    # False、cProfile 静默不开。**顺序是硬要求：先设字段、再调 run_batch_parallel**
    # ——在 run_batch_parallel 内部设置无效，彼时 env 已 pickle 给 worker。
    if args.profile_dir:
        env.profile_enabled = True
        # profile_dir 取 **run 级目录**（<--profile-dir>/<run_id>）：D3 要求 run 级子
        # 目录以隔离同一进程内的多次 run_batch_parallel 调用（no_draw 基线重跑不得
        # 混入主模拟的剖面），而 worker 侧只有这一个字段可用，故把 run_id 折进它的
        # 取值——`6b` 写入与 `6c` 扫描都以 env.profile_dir 为准，两侧口径一致。
        env.profile_dir = os.path.join(args.profile_dir, run_id or '')
        env.profile_skip = args.profile_skip
        env.profile_count = args.profile_count
        # D3：父进程在本次 run_batch_parallel 开始前生成 run 级子目录。
        # D7：目录不可写**一律软降级**——绝不因剖析失败导致模拟失败。
        try:
            os.makedirs(env.profile_dir, exist_ok=True)
        except OSError as exc:
            print(f"警告：profile 目录不可写（{env.profile_dir}）：{exc}——本次不做剖析",
                  file=sys.stderr)
            env.profile_enabled = False
            env.profile_dir = ''

    print("=" * 50)
    print("GachaStat CLI")
    print("=" * 50)
    print(f"Simulations: {args.num_simulations}")
    print(f"Workers: {args.workers}")
    print(f"Seed: {args.seed}")
    print(f"Pity: {'Enabled' if store.pity.enabled else 'Disabled'}")
    if store.pity.enabled and store.pity.pities:
        p0 = store.pity.pities[0]
        print(f"  Type: {p0.btype}")
        if p0.deltas is not None:
            total_n = sum(n for n, _ in p0.deltas)
            print(f"  Deltas: {p0.deltas} (总抽数={total_n})")
        elif p0.threshold is not None:
            print(f"  Threshold: {p0.threshold}")
        if p0.target_featured:
            print("  Target: featured only")
        if p0.counter_init:
            print(f"  Counter Init: {p0.counter_init}")
    print("=" * 50)

    target_specs = {tc.card_id: getattr(tc, 'quantity', 1)
                    for tc in store.target_cards}

    def _cli_progress(done, total):
        if done % max(1, total // 10) == 0 or done >= total:
            print(f"\r  进度: {done}/{total} ({100*done//total}%)", end='', flush=True)

    print(f"\nRunning {args.num_simulations} simulations...")
    start_time = time.time()

    batch_result = run_batch_parallel(
        env=env,
        target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=args.num_simulations,
        max_workers=args.workers,
        seed=args.seed,
        progress_callback=_cli_progress if not args.no_progress else None,
        strategy_key=strategy_key,
        strategy_params=strategy_params,
        # P83 §3.5：只有 --perf-json 才开启采集。关闭时两槽保持空、pickle.dumps
        # 零调用、阶段计时零采集。
        collect_perf=bool(args.perf_json),
    )
    print()  # progress line 换行

    elapsed = time.time() - start_time

    print(f"Completed in {elapsed:.2f}s ({args.num_simulations/elapsed:.1f} sim/s)")

    # ── 不抽卡基线 ──（与 gui/gacha_panel.py:105-124、webui/api.py:307-317 同口径）
    # 两个目的：① 给出「不抽卡时能攒下多少」的对照基准；② 使 cli 的执行流程与
    # GUI/WebUI 一致。P83 的跨路径对比要求流程与开销相同，而基线是另两条入口在主
    # 模拟之后固定要多跑的一次调用（n=1, w=1）；缺了它，cli 的开销与它们不可比。
    # **计时落在 elapsed 之外**：上面的 `Completed in` 仍只反映主模拟，基线单独报。
    # **max_workers=1 是照 GUI 的**：走单进程路径、不建池，故 pool_start 为 0。
    # **P79 裁决**：基线不继承用户停止条件。no_draw 策略全程只返回等待，
    # fixed_action_count 一类条件会把基线截断，final_resources 偏低、基准失真
    # （这是 gui/gacha_panel.py 与 webui/api.py 共同的既有裁决，此处照做）。
    baseline_final = {}
    _baseline_started = time.perf_counter()
    try:
        _baseline_env = copy.deepcopy(env)
        _baseline_env.stop_condition = None
        _baseline_res = run_batch_parallel(
            env=_baseline_env,
            target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=1,
            max_workers=1,
            seed=args.seed,
            strategy_key='no_draw',
        )
        if _baseline_res and _baseline_res[0]:
            baseline_final = dict(_baseline_res[0].get('final_resources', {}) or {})
    except Exception as exc:
        # 与另两条入口的 `except Exception: pass` 有意不同：静默吞掉会让「基线缺失」
        # 与「基线为 0」无从区分，正是 P83 反复在防的静默失效形态，故留一条告警。
        print(f"警告：不抽卡基线计算失败（{exc}），该段对照省略", file=sys.stderr)
    _baseline_elapsed = time.perf_counter() - _baseline_started

    if args.perf_json:
        # `functions` 由本进程内的 pstats 合并填充（`6c`）。`--profile-dir` 未设置时
        # `functions` 与 `run_id` 均为 None——**如实标注，不伪造**（§3.5）。
        functions, merge_warnings = _merge_profile_functions(
            getattr(env, 'profile_dir', '') if getattr(env, 'profile_enabled', False) else None
        )
        for warning in merge_warnings:
            print(f"警告：{warning}", file=sys.stderr)
        _write_perf_json(
            args.perf_json,
            stages=perf_stages,
            packet_bytes=list(getattr(batch_result, 'packet_bytes', []) or []),
            stage_times=dict(getattr(batch_result, 'stage_times', {}) or {}),
            parallel_metrics=dict(getattr(batch_result, 'parallel_metrics', {}) or {}),
            run_id=run_id,
            functions=functions,
        )

    # P61（ISSUE-003）：无 [[targets]] 时兜底目标取 banner 段拼 _ssr（模块级函数，可测）
    actual_target_ids = _fallback_target_ids(store)
    total_targets = len(actual_target_ids)

    total_draws = []
    ssr_counts = []
    gdr_percents = []

    for r in batch_result:
        draws = r.get('total_draws', 0)
        total_draws.append(draws)
        cc = r.get('card_counts', {})
        ssr = sum(cc.get(tid, 0) for tid in actual_target_ids)
        ssr_counts.append(ssr)
        gdr_percents.append((ssr / max(total_targets, 1)) * 100)

    import numpy as np

    print("\n" + "=" * 50)
    print("Results Summary")
    print("=" * 50)
    print(f"Total Simulations: {len(batch_result)}")
    print("\nTotal Draws:")
    print(f"  Mean: {np.mean(total_draws):.1f}")
    print(f"  Median: {np.median(total_draws):.1f}")
    print(f"  Std: {np.std(total_draws):.1f}")

    print("\nSSR Count:")
    print(f"  Mean: {np.mean(ssr_counts):.2f}")
    print(f"  Median: {np.median(ssr_counts):.1f}")

    print("\nGDR (Target Card %):")
    print(f"  Mean: {np.mean(gdr_percents):.2f}%")
    print(f"  Median: {np.median(gdr_percents):.2f}%")
    print(f"  25th percentile: {np.percentile(gdr_percents, 25):.2f}%")
    print(f"  75th percentile: {np.percentile(gdr_percents, 75):.2f}%")

    if baseline_final:
        # 对照基准：同种子、全程不抽卡跑一次，看「什么都不做能攒下多少」。
        print()
        print("No-Draw Baseline (same seed, draws nothing, 1 run):")
        for _k in sorted(baseline_final):
            print(f"  {_k}: {baseline_final[_k]:.1f}")
        print(f"  (baseline run took {_baseline_elapsed:.2f}s)")

    output_data = {
        'config': config_meta,
        'num_simulations': args.num_simulations,
        'elapsed_time': elapsed,
        # 不抽卡基线（同种子、n=1、w=1）。**新增键**，位置与 `summary` 平级——
        # 既有的 config / num_simulations / elapsed_time / summary / extraction
        # 五个键语义与取值均不变。
        'no_draw_baseline': {
            'final_resources': {k: float(v) for k, v in baseline_final.items()},
            'elapsed_time': _baseline_elapsed,
        },
        'summary': {
            'total_draws': {'mean': float(np.mean(total_draws)),
                            'median': float(np.median(total_draws)),
                            'std': float(np.std(total_draws))},
            'ssr_counts': {'mean': float(np.mean(ssr_counts)),
                           'median': float(np.median(ssr_counts))},
            'gdr_percent': {
                'mean': float(np.mean(gdr_percents)),
                'median': float(np.median(gdr_percents)),
                'p25': float(np.percentile(gdr_percents, 25)),
                'p75': float(np.percentile(gdr_percents, 75))
            }
        }
    }

    if args.output_format == 'full' and batch_result.extraction:
        output_data['extraction'] = {
            'n_results': batch_result.extraction.get('n_results', 0),
            'aggregates_count': len(
                batch_result.extraction.get('aggregates', [])),
            'kept_sequences_count': len(
                batch_result.extraction.get('kept_sequences', [])),
            # P61（Ph7 / ISSUE-325）：cumulative_snapshots 键为 banner_id（Ph6
            # pool_end_times 已改 banner 级），非内层 pool_id——展示口径登记
            'cumulative_snapshots_pools': list(
                batch_result.extraction.get('cumulative_snapshots', {}).keys()),
            'transition_flags_count': len(
                batch_result.extraction.get('transition_flags', [])),
        }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to: {args.output}")
    print("=" * 50)


if __name__ == '__main__':
    main()
