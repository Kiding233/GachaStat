"""streaming.py 模块测试——从 test_config_io.py 提取。"""


class TestStreaming:
    """streaming.py 核心类"""

    def test_shared_result_collector_creation(self):
        from gacha_simulator.core.streaming import SharedResultCollector
        collector = SharedResultCollector()
        assert collector is not None
        assert collector.n_results == 0

    def test_extract_aggregate(self):
        from gacha_simulator.core.streaming import extract_aggregate
        from gacha_simulator.core.result_types import CompactResult
        r = CompactResult(
            total_draws=10,
            total_consumed={'draw': 1600.0},
            card_counts={'card_a': 1},
            strategy_name='smart',
        )
        agg = extract_aggregate(r)
        assert agg['total_draws'] == 10
        assert agg['card_counts']['card_a'] == 1

    def test_streaming_success_counter(self):
        from gacha_simulator.core.streaming import StreamingSuccessCounter
        counter = StreamingSuccessCounter(
            target_specs={'card_a': 1},
            gdr_key='all_targets',
            gdr_threshold=1.0,
        )
        assert counter is not None
        assert counter.total == 0

    def test_merge_extraction_packets_empty(self):
        from gacha_simulator.core.streaming import merge_extraction_packets
        result = merge_extraction_packets([])
        assert isinstance(result, dict)
