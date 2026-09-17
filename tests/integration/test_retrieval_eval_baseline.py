"""Phase 3 固定评测集与版本化基线：结果不许悄悄变化，门槛必须真的能拦住退化。"""

from __future__ import annotations

import datetime as clock
import json
from pathlib import Path

import pytest

import retrieval_eval
from retrieval.corpus import load_corpus, load_expansion
from retrieval.indexer import ingest
from retrieval.models import AccessScope, RetrievalQuery
from retrieval.retriever import FtsRetriever
from retrieval.store import ChunkStore

from conftest import REPO_ROOT

pytestmark = pytest.mark.integration

CORPUS_PATH = REPO_ROOT / "knowledge" / "corpus.yaml"
BASELINE_PATH = REPO_ROOT / retrieval_eval.BASELINE_PATH


def evaluate_fts5(tmp_root: Path, eval_set):
    loaded = load_corpus(CORPUS_PATH, repo_root=REPO_ROOT)
    store = ChunkStore(tmp_root / "eval.sqlite3")
    try:
        report = ingest(loaded, store, repo_root=REPO_ROOT)
        lexicon = load_expansion(loaded.policy.expansion, repo_root=REPO_ROOT)
        retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon)
        scope = AccessScope(subject="eval-test", datasets=frozenset(loaded.manifest.dataset_names))
        evaluation = retrieval_eval.evaluate_method(
            method="fts5",
            retrieve=lambda request: retriever.retrieve(request, scope),
            eval_set=eval_set,
            index_version=store.index_version,
            now=clock.datetime.now(clock.timezone.utc),
        )
        payload = {
            "eval_set_version": eval_set.version,
            "corpus": {
                "path": loaded.corpus_path,
                "version": loaded.manifest.version,
                "input_hash": loaded.input_hash,
                "datasets": list(loaded.manifest.dataset_names),
                "entries": len(loaded.entries),
            },
            "index": {
                "documents": store.stats().documents,
                "chunks": store.stats().chunks,
                "run_status": report.status.value,
            },
            "thresholds": eval_set.thresholds.model_dump(),
            "methods": [evaluation.model_dump()],
        }
        return evaluation, payload
    finally:
        store.close()


def test_recorded_baseline_matches_current_evaluation(tmp_root: Path) -> None:
    """记录在案的基线（tests/fixtures/retrieval_eval/baseline-v2.json）必须与当前实现一致。

    排名、指标或查询词项发生变化时这条用例会失败：要么修回行为，
    要么显式用 python tools/retrieval_eval.py --record ... 重新记录基线并递增评测集版本。
    """

    assert BASELINE_PATH.is_file(), "缺少版本化基线；先运行 tools/retrieval_eval.py --record"
    eval_set = retrieval_eval.load_eval_set()
    _, payload = evaluate_fts5(tmp_root, eval_set)
    current = json.loads(json.dumps(retrieval_eval.baseline_record(payload), ensure_ascii=False))
    recorded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    # 基线里同时记录了对照用的向量检索；这里只比较**门槛适用的** FTS5 基线
    # （向量方法由 tools/retrieval_eval.py --method both 在 CI 里对照记录）。
    recorded_fts5 = {
        **recorded,
        "methods": [item for item in recorded["methods"] if item["method"] == "fts5"],
    }
    assert retrieval_eval.diff_baseline(recorded_fts5, current) == []


def test_thresholds_are_real_gates(tmp_root: Path) -> None:
    """把门槛调严必须判定失败：证明门槛不是装饰，评测真的在算。"""

    eval_set = retrieval_eval.load_eval_set()
    strict = eval_set.model_copy(
        update={"thresholds": eval_set.thresholds.model_copy(update={"min_precision_at_k": 0.99})}
    )
    evaluation, _ = evaluate_fts5(tmp_root, strict)
    assert evaluation.passed is False
    assert any("precision" in item for item in evaluation.failures)

    baseline, _ = evaluate_fts5(tmp_root, eval_set)
    assert baseline.passed is True


def test_eval_set_covers_documented_queries() -> None:
    """评测集必须覆盖数据源文档里列出的七个主题，且每个查询都可判定。"""

    eval_set = retrieval_eval.load_eval_set()
    assert eval_set.version == 2
    assert len(eval_set.queries) == 7
    for query in eval_set.queries:
        assert query.expected_documents, f"{query.id} 缺少期望文档"
        assert query.supporting_terms, f"{query.id} 缺少 supporting_terms（无法判定片段是否自足）"
        for document in query.expected_documents:
            dataset, _, path = document.partition(":")
            assert dataset and path.endswith(".md"), document
    identifiers = [query.id for query in eval_set.queries]
    assert identifiers == sorted(set(identifiers))
