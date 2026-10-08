"""Phase 1 性能基线测试：固定种子生成规则，记录匹配耗时与内存。

这里只建立基线，不做优化、不加缓存：断言的是"结论稳定"与"没有数量级退化"，
而不是一个精确的时间数字（CI 机器负载不同，精确断言必然不稳定）。
"""

from __future__ import annotations

import time

import pytest

from policy.engine import evaluate

import policy_bench
from policy_bench import DEFAULT_SEED, generate_contexts, generate_rules, measure

pytestmark = pytest.mark.integration

# 宽松上限：本机 1000 条规则约 40ms/次；超过 10 倍说明出现了数量级退化。
# 这个上限按**本进程的 CPU 时间**判（time.process_time），不按墙钟：门禁的 pytest 步骤
# 是按文件并行的（-n auto），别的进程抢 CPU 时墙钟会被拉长数倍（Windows 本机实测 597ms/次），
# 而 CPU 时间几乎不变（VM 实测：空闲 62ms；4 个满载进程抢 2 核时墙钟 155ms、CPU 仍 63ms）。
# 墙钟照旧由 measure() 记录、打印、写进基线——只是不再拿它当门槛。
MS_PER_EVALUATION_CEILING = 400.0


def cpu_ms_per_evaluation(count: int, *, context_count: int = 5) -> float:
    """同一组固定的规则 / 上下文，按 CPU 时间量每次匹配的毫秒数（只量 evaluate 本身）。

    规则吃种子；上下文不吃（按编号构造），所以这里只给规则传 seed。
    """

    rules = generate_rules(count, seed=DEFAULT_SEED)
    contexts = generate_contexts(context_count)
    started = time.process_time()
    for context in contexts:
        evaluate(rules, context)
    return (time.process_time() - started) * 1000 / len(contexts)


def test_generator_is_deterministic_and_seed_sensitive() -> None:
    first = generate_rules(50, seed=DEFAULT_SEED)
    again = generate_rules(50, seed=DEFAULT_SEED)
    other_seed = generate_rules(50, seed=DEFAULT_SEED + 1)

    assert first.identity == again.identity
    assert first.model_dump() == again.model_dump()
    assert first.identity != other_seed.identity
    assert len(first) == 50
    assert len(set(first.ids)) == 50


def test_generated_contexts_are_fixed() -> None:
    first = generate_contexts(5)
    again = generate_contexts(5)

    assert [item.model_dump() for item in first] == [item.model_dump() for item in again]
    assert all(item.dependencies for item in first)


def test_generator_rejects_negative_counts() -> None:
    with pytest.raises(ValueError):
        generate_rules(-1)


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_baseline_is_recorded_for_fixed_sizes(count: int, capsys: pytest.CaptureFixture[str]) -> None:
    sample = measure(count, seed=DEFAULT_SEED, context_count=5, repeats=1)

    print(
        f"rules={sample['rules']} evals={sample['evaluations']} "
        f"total={sample['total_seconds']}s ms/eval={sample['ms_per_evaluation']} "
        f"peak={sample['peak_kib']}KiB matched={sample['matched_rules_total']} "
        f"violations={sample['violations_total']}"
    )

    assert sample["rules"] == count
    assert sample["evaluations"] == 5
    assert sample["rule_set_hash"] == generate_rules(count, seed=DEFAULT_SEED).identity
    assert sample["matched_rules_total"] > 0
    assert sample["peak_kib"] > 0
    assert sample["ms_per_evaluation"] > 0  # 墙钟照旧记录（不当门槛，见 MS_PER_EVALUATION_CEILING）
    cpu_ms = cpu_ms_per_evaluation(count)
    assert cpu_ms < MS_PER_EVALUATION_CEILING, (
        f"CPU {cpu_ms:.1f}ms/次 超过上限 {MS_PER_EVALUATION_CEILING}ms（墙钟 "
        f"{sample['ms_per_evaluation']}ms/次）：这是数量级退化，不是并行负载"
    )


def test_evaluation_repeats_give_identical_conclusions() -> None:
    rules = generate_rules(200, seed=DEFAULT_SEED)
    contexts = generate_contexts(5)

    first = [evaluate(rules, context).to_decision_dict() for context in contexts]
    second = [evaluate(rules, context).to_decision_dict() for context in contexts]

    assert first == second
    assert {item["decision"] for item in first} <= {"allow", "allow_with_warnings", "block"}


def test_baseline_payload_is_json_serializable() -> None:
    import json

    baseline = policy_bench.run_baseline((10,), seed=DEFAULT_SEED)

    assert json.loads(json.dumps(baseline))["samples"][0]["rules"] == 10
    assert baseline["seed"] == DEFAULT_SEED
