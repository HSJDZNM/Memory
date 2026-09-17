"""规则匹配性能基线：固定随机种子生成规则，记录匹配耗时与内存。

只建立基线，不做优化，也不引入缓存。证据由 tools/phase_evidence.py 写入
`.tmp/artifacts/phase-1-evidence.json` 的 performance 段，测试则用同一份生成器
断言"相同种子 → 相同规则集 → 相同决定"。

用法：

    python tools/policy_bench.py                  # 10 / 100 / 1000 条规则
    python tools/policy_bench.py --counts 100
    python tools/policy_bench.py --json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from policy.engine import evaluate  # noqa: E402
from policy.models import (  # noqa: E402
    Enforcement,
    EnforcementType,
    ForbiddenDependencyRule,
    PolicyContext,
    Rule,
    RuleScope,
    RuleSet,
    Severity,
    SourceRef,
)

__all__ = [
    "DEFAULT_COUNTS",
    "DEFAULT_SEED",
    "generate_contexts",
    "generate_rules",
    "measure",
    "run_baseline",
]

DEFAULT_SEED = 20260101
DEFAULT_COUNTS = (10, 100, 1000)
DEFAULT_CONTEXT_COUNT = 20
DEFAULT_REPEATS = 3

LAYERS = ("controller", "service", "repository", "model", "util")
SEVERITIES = (Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL)
SELECTOR_SHAPES = ("exact", "list", "wildcard", "module")


def _scope_for(index: int, offset: int) -> RuleScope:
    """四种范围形状轮换，确保基线覆盖精确值、列表、通配与缺值分支。"""

    shape = SELECTOR_SHAPES[index % len(SELECTOR_SHAPES)]
    layer = LAYERS[(index + offset) % len(LAYERS)]
    if shape == "exact":
        return RuleScope(language="python", layer=layer)
    if shape == "list":
        return RuleScope(layer=[layer, LAYERS[(index + offset + 1) % len(LAYERS)]])
    if shape == "wildcard":
        return RuleScope(layer="*")
    return RuleScope(module=f"module-{index % 7:02d}")


def generate_rules(count: int, *, seed: int = DEFAULT_SEED) -> RuleSet:
    """生成 count 条简单规则；相同种子必然得到相同规则集与相同哈希。"""

    if count < 0:
        raise ValueError("count 不能为负数")
    # 种子决定层偏移量，并写进规则描述：既保证"同种子 → 同规则集"，又让不同种子产生不同哈希。
    offset = random.Random(seed).randrange(len(LAYERS))
    rules: list[Rule] = []
    for index in range(count):
        number = index + 1
        rules.append(
            Rule(
                id=f"BENCH-{number:04d}",
                version=1,
                name=f"benchmark-rule-{number:04d}",
                description=f"性能基线用的合成规则（seed={seed}）",
                scope=_scope_for(index, offset),
                severity=SEVERITIES[index % len(SEVERITIES)],
                enforcement=Enforcement(
                    type=EnforcementType.DETERMINISTIC, checker="forbidden_dependency"
                ),
                rule=ForbiddenDependencyRule(
                    forbidden_dependency=(f"dep-{number:04d}", "repository")
                ),
                message="性能基线规则：禁止直接依赖合成依赖。",
                source=SourceRef(kind="project-policy", path="tools/policy_bench.py"),
            )
        )
    return RuleSet(rules=tuple(rules))


def generate_contexts(count: int, *, seed: int = DEFAULT_SEED) -> tuple[PolicyContext, ...]:
    """生成固定的一组上下文；依赖编号与规则编号对齐，保证有真实命中。"""

    contexts: list[PolicyContext] = []
    for index in range(count):
        module_number = index % 7
        dependencies = [f"dep-{index + 1:04d}", f"dep-{index + 2:04d}", "repository"]
        contexts.append(
            PolicyContext(
                request_id=f"bench-{index:04d}",
                file=f"src/{LAYERS[index % len(LAYERS)]}/module-{module_number:02d}/file.py",
                language="python",
                layer=LAYERS[(index + 2) % len(LAYERS)],
                module=f"module-{module_number:02d}",
                operation=None,
                dependencies=tuple(dependencies),
                trace_id=f"trace-bench-{index:04d}",
            )
        )
    return tuple(contexts)


def measure(
    count: int,
    *,
    seed: int = DEFAULT_SEED,
    context_count: int = DEFAULT_CONTEXT_COUNT,
    repeats: int = DEFAULT_REPEATS,
) -> dict[str, Any]:
    """测量 count 条规则对固定上下文的匹配耗时与内存峰值。"""

    rules = generate_rules(count, seed=seed)
    contexts = generate_contexts(context_count, seed=seed)

    tracemalloc.start()
    started = time.perf_counter()
    matched = 0
    violations = 0
    for _ in range(repeats):
        for context in contexts:
            result = evaluate(rules, context)
            matched += len(result.matched_rules)
            violations += len(result.violations)
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    evaluations = repeats * len(contexts)
    return {
        "rules": count,
        "contexts": len(contexts),
        "repeats": repeats,
        "evaluations": evaluations,
        "total_seconds": round(elapsed, 6),
        "ms_per_evaluation": round(elapsed * 1000 / evaluations, 6),
        "peak_kib": round(peak_bytes / 1024, 3),
        "matched_rules_total": matched,
        "violations_total": violations,
        "rule_set_hash": rules.identity,
    }


def run_baseline(
    counts: Iterable[int] = DEFAULT_COUNTS, *, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    return {
        "seed": seed,
        "counts": list(counts),
        "samples": [measure(count, seed=seed) for count in counts],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="规则匹配性能基线（只记录，不做优化）")
    parser.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=list(DEFAULT_COUNTS),
        help="规则条数，可写多个；默认 10 100 1000",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="固定随机种子")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    baseline = run_baseline(args.counts, seed=args.seed)
    if args.json:
        print(json.dumps(baseline, ensure_ascii=False, indent=2))
        return 0

    print(f"seed={baseline['seed']}（固定种子，结果可复现）")
    print(f"{'rules':>6} {'evals':>6} {'total(s)':>10} {'ms/eval':>10} {'peakKiB':>9} {'matched':>8} {'violations':>11}")
    for sample in baseline["samples"]:
        print(
            f"{sample['rules']:>6} {sample['evaluations']:>6} {sample['total_seconds']:>10.4f} "
            f"{sample['ms_per_evaluation']:>10.4f} {sample['peak_kib']:>9.1f} "
            f"{sample['matched_rules_total']:>8} {sample['violations_total']:>11}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
