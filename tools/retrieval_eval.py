"""Phase 3 固定评测集基线：FTS5（以及可选的向量检索）在同一数据集上的可解释对比。

用法：

    python tools/retrieval_eval.py                  # FTS5 基线 + 门槛判定
    python tools/retrieval_eval.py --method vector  # 同一评测集上的向量检索（含建向量）
    python tools/retrieval_eval.py --method both --json

门槛写在评测集 fixture 里（tests/fixtures/retrieval_eval/queries.yaml），
代码中不出现"脱离数据的常数"；本脚本只做计算、记录与判定。

输出：
    .tmp/artifacts/phase-3-retrieval-baseline.json   # 结论（被 tools/phase_evidence.py 引用）
退出码：
    0 = 门槛全部满足；1 = 有门槛未满足；2 = 配置或执行错误
"""

from __future__ import annotations

import argparse
import datetime as clock
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
for directory in (SRC_DIR,):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from retrieval.context import ContextBuilder, render_context  # noqa: E402
from retrieval.corpus import load_corpus, load_expansion  # noqa: E402
from retrieval.indexer import ingest  # noqa: E402
from retrieval.models import (  # noqa: E402
    AccessScope,
    PolicyFact,
    RetrievalQuery,
    RetrievalStatus,
)
from retrieval.retriever import FtsRetriever, ResultCache, hits_to_chunks  # noqa: E402
from retrieval.store import ChunkStore  # noqa: E402
from retrieval.vector import VectorRetriever  # noqa: E402

CORPUS_PATH = "knowledge/corpus.yaml"
EVAL_PATH = "tests/fixtures/retrieval_eval/queries.yaml"
BASELINE_PATH = "tests/fixtures/retrieval_eval/baseline-v3.json"
ARTIFACT_PATH = ".tmp/artifacts/phase-3-retrieval-baseline.json"
DEFAULT_DB = ".tmp/retrieval/eval-index.sqlite3"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvalQuery(StrictModel):
    id: str
    text: str
    expected_documents: Tuple[str, ...]
    supporting_terms: Tuple[str, ...] = ()
    reference_documents: Tuple[str, ...] = Field(
        default=(),
        description=(
            "计划书的数据源映射里点名的来源：只记录它们当前的排名（reference_rank），"
            "不作为门槛。语料扩充后正确答案集合会变大，这个字段让「原来的来源掉到第几名」依然可见。"
        ),
    )
    notes: str = ""


class EvalThresholds(StrictModel):
    top_k: int = Field(default=5, ge=1, le=20)
    hit_at_k: float = Field(default=1.0, ge=0.0, le=1.0)
    support_at_k: float = Field(default=1.0, ge=0.0, le=1.0)
    source_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    order_stable: bool = True
    min_precision_at_k: float = Field(default=0.0, ge=0.0, le=1.0)
    min_recall_at_k: float = Field(default=0.0, ge=0.0, le=1.0)


class EvalSet(StrictModel):
    version: int = Field(ge=1)
    thresholds: EvalThresholds = Field(default_factory=EvalThresholds)
    queries: Tuple[EvalQuery, ...] = ()


class QueryOutcome(StrictModel):
    id: str
    text: str
    status: str
    results: Tuple[str, ...] = ()
    first_expected_rank: Optional[int] = None
    supporting_rank: Optional[int] = None
    reference_rank: Optional[int] = None
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    sources_complete: bool = False
    order_stable: bool = True
    plan_terms: Tuple[str, ...] = ()


class MethodReport(StrictModel):
    method: str
    index_version: str
    top_k: int
    outcomes: Tuple[QueryOutcome, ...] = ()
    hit_rate: float = 0.0
    support_rate: float = 0.0
    mean_precision_at_k: float = 0.0
    mean_recall_at_k: float = 0.0
    source_completeness: float = 0.0
    order_stable: bool = True
    failures: Tuple[str, ...] = ()
    passed: bool = False
    timestamp: str = ""


def baseline_record(payload: dict[str, Any]) -> dict[str, Any]:
    """从一次评测结果里抽出**可版本化的稳定部分**：排名、指标与门槛，不含时间戳与具体分数。"""

    return {
        "eval_set_version": payload.get("eval_set_version"),
        "corpus": {
            key: payload.get("corpus", {}).get(key)
            for key in ("path", "version", "input_hash", "datasets", "entries")
        },
        "index": {
            key: payload.get("index", {}).get(key)
            for key in ("documents", "chunks", "run_status")
        },
        "thresholds": payload.get("thresholds"),
        "methods": [
            {
                "method": item.get("method"),
                "top_k": item.get("top_k"),
                "hit_rate": item.get("hit_rate"),
                "support_rate": item.get("support_rate"),
                "mean_precision_at_k": item.get("mean_precision_at_k"),
                "mean_recall_at_k": item.get("mean_recall_at_k"),
                "source_completeness": item.get("source_completeness"),
                "order_stable": item.get("order_stable"),
                "passed": item.get("passed"),
                "outcomes": [
                    {
                        "id": outcome.get("id"),
                        "status": outcome.get("status"),
                        "results": outcome.get("results"),
                        "first_expected_rank": outcome.get("first_expected_rank"),
                        "supporting_rank": outcome.get("supporting_rank"),
                        "reference_rank": outcome.get("reference_rank"),
                        "plan_terms": outcome.get("plan_terms"),
                    }
                    for outcome in item.get("outcomes", [])
                ],
            }
            for item in payload.get("methods", [])
        ],
    }


def diff_baseline(recorded: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """比较记录在案的基线与本次结果；只比较稳定字段（排名、指标、词项），不比较分数与时间。"""

    differences: list[str] = []
    for key in ("eval_set_version", "thresholds", "corpus", "index"):
        if recorded.get(key) != current.get(key):
            differences.append(f"{key} 变化：recorded={recorded.get(key)!r} current={current.get(key)!r}")
    recorded_methods = {item.get("method"): item for item in recorded.get("methods", [])}
    current_methods = {item.get("method"): item for item in current.get("methods", [])}
    for name, item in current_methods.items():
        previous = recorded_methods.get(name)
        if previous is None:
            differences.append(f"{name}: 记录在案的基线里没有这个方法（需要重新记录）")
            continue
        for key in (
            "hit_rate",
            "support_rate",
            "mean_precision_at_k",
            "mean_recall_at_k",
            "source_completeness",
            "order_stable",
            "top_k",
        ):
            if previous.get(key) != item.get(key):
                differences.append(
                    f"{name}.{key} 变化：recorded={previous.get(key)!r} current={item.get(key)!r}"
                )
        previous_outcomes = {entry.get("id"): entry for entry in previous.get("outcomes", [])}
        for entry in item.get("outcomes", []):
            old = previous_outcomes.get(entry.get("id"))
            if old is None:
                differences.append(f"{name}.{entry.get('id')}: 基线里没有这个查询")
                continue
            for key in (
                "status",
                "results",
                "first_expected_rank",
                "supporting_rank",
                "reference_rank",
                "plan_terms",
            ):
                if old.get(key) != entry.get(key):
                    differences.append(
                        f"{name}.{entry.get('id')}.{key} 变化："
                        f"recorded={old.get(key)!r} current={entry.get(key)!r}"
                    )
    for name in recorded_methods:
        if name not in current_methods:
            differences.append(f"{name}: 本次没有评测这个方法（记录在案的基线无法比较）")
    return differences


def load_eval_set(path: Path | str = EVAL_PATH) -> EvalSet:
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    try:
        return EvalSet.model_validate(document)
    except ValidationError as error:
        raise SystemExit(f"评测集校验失败 {target}: {error}") from error


def document_key(result: Any) -> str:
    return f"{result.dataset}:{result.source_path}"


def _supporting(result: Any, query: EvalQuery) -> bool:
    haystack = (result.text + " " + " > ".join(result.heading_path)).lower()
    return any(term.lower() in haystack for term in query.supporting_terms)


def evaluate_query(
    query: EvalQuery,
    retrieve: Callable[[RetrievalQuery], Any],
    *,
    top_k: int,
    repeat: int = 2,
) -> QueryOutcome:
    """跑一个查询（默认跑两次用于稳定性判定），返回可比较的结构化结论。"""

    expected = set(query.expected_documents)
    # 多取一些结果：门槛只看 top_k，但 reference_rank 需要知道"原来的来源掉到第几名"。
    request = RetrievalQuery(text=query.text, limit=max(top_k * 3, top_k))
    first = retrieve(request)
    second = retrieve(request) if repeat > 1 else first

    all_results = first.results
    results = tuple(item for item in all_results if item.rank <= top_k)
    keys = tuple(document_key(item) for item in results)
    # 稳定性比较完整排名（含 top_k 之外），两边口径必须一致。
    stability = tuple((item.rank, item.chunk_id) for item in all_results) == tuple(
        (item.rank, item.chunk_id) for item in second.results
    )
    expected_hits = [item for item in results if document_key(item) in expected]
    supporting_rank = next(
        (item.rank for item in expected_hits if _supporting(item, query)), None
    )
    references = set(query.reference_documents)
    reference_rank = next(
        (item.rank for item in all_results if document_key(item) in references), None
    )
    sources_complete = bool(results) and all(
        item.source_path and item.source_url and item.license and item.text_hash for item in results
    )
    return QueryOutcome(
        id=query.id,
        text=query.text,
        status=first.status.value,
        results=keys,
        first_expected_rank=(expected_hits[0].rank if expected_hits else None),
        supporting_rank=supporting_rank,
        reference_rank=reference_rank,
        precision_at_k=(len(expected_hits) / len(results)) if results else 0.0,
        recall_at_k=(len({document_key(item) for item in expected_hits}) / len(expected))
        if expected
        else 0.0,
        sources_complete=sources_complete,
        order_stable=stability,
        plan_terms=(first.plan.terms if first.plan is not None else ()),
    )


def evaluate_method(
    *,
    method: str,
    retrieve: Callable[[RetrievalQuery], Any],
    eval_set: EvalSet,
    index_version: str,
    now: clock.datetime,
) -> MethodReport:
    outcomes = tuple(
        evaluate_query(query, retrieve, top_k=eval_set.thresholds.top_k)
        for query in eval_set.queries
    )
    thresholds = eval_set.thresholds
    total = len(outcomes) or 1
    hit_rate = sum(1 for item in outcomes if item.first_expected_rank is not None) / total
    support_rate = sum(1 for item in outcomes if item.supporting_rank is not None) / total
    mean_precision = sum(item.precision_at_k for item in outcomes) / total
    mean_recall = sum(item.recall_at_k for item in outcomes) / total
    completeness = sum(1 for item in outcomes if item.sources_complete) / total
    stable = all(item.order_stable for item in outcomes)

    failures: list[str] = []
    for item in outcomes:
        if item.first_expected_rank is None:
            failures.append(f"{item.id}: 期望文档没有进入 top {thresholds.top_k}（status={item.status}）")
        elif item.first_expected_rank > thresholds.top_k:
            failures.append(
                f"{item.id}: 期望文档的最佳排名 {item.first_expected_rank} > {thresholds.top_k}"
            )
        if item.supporting_rank is None:
            failures.append(f"{item.id}: top {thresholds.top_k} 里没有能独立支持答案的片段")
        if not item.sources_complete and item.results:
            failures.append(f"{item.id}: 返回项缺少来源或哈希")
        if not item.order_stable:
            failures.append(f"{item.id}: 连续两次运行排名不一致")
    if hit_rate < thresholds.hit_at_k:
        failures.append(f"hit@{thresholds.top_k} = {hit_rate:.3f} < {thresholds.hit_at_k}")
    if support_rate < thresholds.support_at_k:
        failures.append(f"support@{thresholds.top_k} = {support_rate:.3f} < {thresholds.support_at_k}")
    if completeness < thresholds.source_completeness:
        failures.append(f"source_completeness = {completeness:.3f} < {thresholds.source_completeness}")
    if thresholds.order_stable and not stable:
        failures.append("order_stable = false")
    if mean_precision + 1e-9 < thresholds.min_precision_at_k:
        failures.append(f"precision@{thresholds.top_k} = {mean_precision:.3f} < {thresholds.min_precision_at_k}")
    if mean_recall + 1e-9 < thresholds.min_recall_at_k:
        failures.append(f"recall@{thresholds.top_k} = {mean_recall:.3f} < {thresholds.min_recall_at_k}")

    return MethodReport(
        method=method,
        index_version=index_version,
        top_k=thresholds.top_k,
        outcomes=outcomes,
        hit_rate=hit_rate,
        support_rate=support_rate,
        mean_precision_at_k=mean_precision,
        mean_recall_at_k=mean_recall,
        source_completeness=completeness,
        order_stable=stable,
        failures=tuple(failures),
        passed=not failures,
        timestamp=now.isoformat().replace("+00:00", "Z"),
    )


def build_store(*, db_path: Path, rebuild: bool) -> Tuple[ChunkStore, Any, Any, Any]:
    loaded = load_corpus(CORPUS_PATH, repo_root=REPO_ROOT)
    if rebuild and db_path.exists():
        db_path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db_path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
    store = ChunkStore(db_path)
    report = ingest(loaded, store, repo_root=REPO_ROOT)
    lexicon = (
        load_expansion(loaded.policy.expansion, repo_root=REPO_ROOT)
        if loaded.policy.expansion
        else None
    )
    return store, loaded, lexicon, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 固定评测集基线")
    parser.add_argument("--method", choices=("fts5", "vector", "both"), default="fts5")
    parser.add_argument("--db", default=DEFAULT_DB, help="索引库路径（默认 .tmp/ 下，可随时重建）")
    parser.add_argument("--out", default=ARTIFACT_PATH)
    parser.add_argument("--rebuild", action="store_true", help="先删除索引库再重建")
    parser.add_argument(
        "--baseline",
        default=BASELINE_PATH,
        help="记录在案的基线（排名与指标）；与本次结果不一致即判定失败，除非用 --record 重新记录",
    )
    parser.add_argument(
        "--record",
        default=None,
        metavar="PATH",
        help="把本次结果记录成基线（显式动作，用来更新版本化结果；通常是 tests/fixtures/retrieval_eval/baseline-v1.json）",
    )
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 报告")
    parser.add_argument(
        "--gate",
        choices=("fts5", "vector", "both"),
        default="fts5",
        help="哪个方法的门槛决定退出码；其余方法照常记录但仅供参考（默认 fts5 基线）",
    )
    args = parser.parse_args(argv)

    now = clock.datetime.now(clock.timezone.utc)
    db_path = REPO_ROOT / args.db
    store, loaded, lexicon, ingest_report = build_store(db_path=db_path, rebuild=args.rebuild)
    scope = AccessScope(subject="eval-harness", datasets=frozenset(loaded.manifest.dataset_names))
    eval_set = load_eval_set()

    def fts_retrieve(request: RetrievalQuery) -> Any:
        retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=ResultCache())
        return retriever.retrieve(request, scope)

    def vector_retrieve(request: RetrievalQuery) -> Any:
        retriever = VectorRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=ResultCache())
        retriever.build()
        return retriever.retrieve(request, scope)

    reports: list[MethodReport] = []
    if args.method in ("fts5", "both"):
        reports.append(
            evaluate_method(
                method="fts5",
                retrieve=fts_retrieve,
                eval_set=eval_set,
                index_version=store.index_version,
                now=now,
            )
        )
    if args.method in ("vector", "both"):
        reports.append(
            evaluate_method(
                method="vector",
                retrieve=vector_retrieve,
                eval_set=eval_set,
                index_version=store.index_version,
                now=now,
            )
        )

    context_probe = _context_probe(store, loaded, lexicon, scope)
    gated = [report for report in reports if report.method in _gate_methods(args.gate)]
    comparison = _comparison(reports)

    payload: dict[str, Any] = {
        "phase": 3,
        "eval_set_version": eval_set.version,
        "eval_set": EVAL_PATH,
        "corpus": {
            "path": loaded.corpus_path,
            "version": loaded.manifest.version,
            "input_hash": loaded.input_hash,
            "datasets": list(loaded.manifest.dataset_names),
            "entries": len(loaded.entries),
            "licenses": {
                dataset.name: dataset.license for dataset in loaded.manifest.datasets
            },
        },
        "index": {
            "path": args.db,
            "documents": store.stats().documents,
            "chunks": store.stats().chunks,
            "index_version": store.index_version,
            "run_id": ingest_report.run_id,
            "run_status": ingest_report.status.value,
        },
        "thresholds": eval_set.thresholds.model_dump(),
        "methods": [report.model_dump() for report in reports],
        "context_probe": context_probe,
        "gated_methods": list(_gate_methods(args.gate)),
        "comparison": comparison,
        "result": "pass" if all(report.passed for report in gated) else "fail",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
    }
    # 统一成 JSON 形态再比较：记录在案的是 JSON 数组，内存里是元组，直接比较会全是假差异。
    record = json.loads(json.dumps(baseline_record(payload), ensure_ascii=False))
    baseline_path = REPO_ROOT / args.baseline
    drift: list[str] = []
    if args.record:
        recorded_path = REPO_ROOT / args.record
        recorded_path.parent.mkdir(parents=True, exist_ok=True)
        recorded_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        payload["baseline"] = {
            "path": args.record,
            "action": "recorded",
            "drift": [],
        }
        print("已记录基线:", recorded_path.relative_to(REPO_ROOT).as_posix())
    elif baseline_path.is_file():
        recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
        drift = diff_baseline(recorded, record)
        payload["baseline"] = {
            "path": args.baseline,
            "action": "compared",
            "drift": drift,
        }
        if drift:
            payload["result"] = "fail"
    else:
        payload["baseline"] = {
            "path": args.baseline,
            "action": "missing",
            "drift": [],
            "hint": "还没有版本化基线，可用 --record tests/fixtures/retrieval_eval/baseline-v1.json 记录",
        }

    output = REPO_ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render(reports, eval_set, store, gated=args.gate))
        if drift:
            print()
            print("与记录在案的基线不一致（需要重新记录基线，或修回行为）：")
            for item in drift:
                print("  ! " + item)
        print("artifact: " + output.relative_to(REPO_ROOT).as_posix())
    return 0 if payload["result"] == "pass" else 1


def _gate_methods(gate: str) -> Tuple[str, ...]:
    return ("fts5", "vector") if gate == "both" else (gate,)


def _comparison(reports: Sequence[MethodReport]) -> dict[str, Any]:
    """FTS5 基线与向量检索的可解释对比：只在向量全面不劣且通过门槛时才采纳。"""

    baseline = next((item for item in reports if item.method == "fts5"), None)
    vector = next((item for item in reports if item.method == "vector"), None)
    if baseline is None or vector is None:
        return {"available": False, "reason": "只跑了单一方法，未做对照"}
    not_worse = (
        vector.hit_rate >= baseline.hit_rate
        and vector.support_rate >= baseline.support_rate
        and vector.mean_precision_at_k >= baseline.mean_precision_at_k
    )
    adopted = bool(vector.passed and not_worse)
    if adopted:
        reason = "向量检索通过全部门槛且不劣于 FTS5 基线，可以进入下一轮复评"
    elif not vector.passed:
        reason = "向量检索未通过门槛（见 failures），因此不采纳；端口与实现保留，等可固定版本的 embedding 出现后用同一评测集复评"
    else:
        reason = "向量检索虽通过门槛但未优于 FTS5 基线，收益不足以引入额外依赖与运维成本"
    return {
        "available": True,
        "vector_adopted": adopted,
        "vector_not_worse": not_worse,
        "baseline": {
            "method": baseline.method,
            "hit_at_k": baseline.hit_rate,
            "support_at_k": baseline.support_rate,
            "precision_at_k": baseline.mean_precision_at_k,
            "recall_at_k": baseline.mean_recall_at_k,
        },
        "candidate": {
            "method": vector.method,
            "hit_at_k": vector.hit_rate,
            "support_at_k": vector.support_rate,
            "precision_at_k": vector.mean_precision_at_k,
            "recall_at_k": vector.mean_recall_at_k,
            "failures": list(vector.failures),
        },
        "reason": reason,
    }


def _context_probe(store: ChunkStore, loaded: Any, lexicon: Any, scope: AccessScope) -> dict[str, Any]:
    """顺手验证"查询 → chunk → 来源 → Context"的完整链路仍然成立。"""

    retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon)
    result = retriever.retrieve(RetrievalQuery(text="代码评审需要检查哪些方面"), scope)
    builder = ContextBuilder.from_policy(loaded.policy)
    context = builder.build(
        retrieval=result,
        policy_facts=(
            PolicyFact(
                rule_id="ARCH-001@1",
                severity="error",
                message="Controller 必须通过 Service 访问 Repository。",
                source_path="policies/architecture/ARCH-001.yaml",
            ),
        ),
        request_id="eval-context-probe",
    )
    rendered = render_context(context)
    return {
        "status": context.status.value,
        "snippets": len(context.snippets),
        "citations": list(context.citations),
        "used_chars": context.used_chars,
        "budget_chars": context.budget_chars,
        "every_snippet_has_source": all(
            item.source_path and item.source_url and item.license and item.text_hash
            for item in context.snippets
        ),
        "rendered_within_budget": len(rendered) <= context.budget_chars,
        "policy_facts_first": rendered.index("[P1]") < rendered.index("[K1]")
        if context.snippets
        else None,
        "reference_marked_untrusted": "不可信数据" in rendered,
    }


def _render(
    reports: Sequence[MethodReport], eval_set: EvalSet, store: ChunkStore, *, gated: str = "fts5"
) -> str:
    lines = [
        f"eval set v{eval_set.version} | top_k={eval_set.thresholds.top_k} | "
        f"index={store.index_version[:22]}... | documents={store.stats().documents} "
        f"chunks={store.stats().chunks}",
    ]
    for report in reports:
        lines.append("")
        marker = "" if report.method in _gate_methods(gated) else "（仅供参考，不决定退出码）"
        lines.append(
            f"[{report.method}]{marker} hit@k={report.hit_rate:.2f} support@k={report.support_rate:.2f} "
            f"precision@k={report.mean_precision_at_k:.3f} recall@k={report.mean_recall_at_k:.3f} "
            f"sources={report.source_completeness:.2f} stable={report.order_stable} "
            f"-> {'PASS' if report.passed else 'FAIL'}"
        )
        for item in report.outcomes:
            first = "—" if item.first_expected_rank is None else str(item.first_expected_rank)
            support = "—" if item.supporting_rank is None else str(item.supporting_rank)
            reference = "—" if item.reference_rank is None else str(item.reference_rank)
            lines.append(
                f"   {item.id}: status={item.status:11s} expected@{first:>2s} "
                f"support@{support:>2s} p={item.precision_at_k:.2f} r={item.recall_at_k:.2f} "
                f"reference@{reference:>2s}"
            )
        for failure in report.failures:
            lines.append("   ! " + failure)
    return chr(10).join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
