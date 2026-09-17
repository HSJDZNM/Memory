"""Phase 3 CLI 集成测试：真实子进程、退出码、JSON 载荷与"知识不可用"路径。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, load_fixture_corpus, write_fixture_corpus

pytestmark = pytest.mark.integration

DECISION_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "decisions" / "block.json"


def env() -> dict[str, str]:
    values = dict(os.environ)
    values["PYTHONPATH"] = str(REPO_ROOT / "src")
    values["PYTHONIOENCODING"] = "utf-8"
    return values


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "retrieval.cli", *args],
        cwd=REPO_ROOT,
        env=env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.fixture()
def cli_project(tmp_root: Path) -> Path:
    """在临时目录里准备夹具语料，返回它的 corpus.yaml 路径。"""

    return write_fixture_corpus(tmp_root)


def base_args(tmp_root: Path, corpus: Path) -> list[str]:
    return [
        "--root",
        str(tmp_root),
        "--corpus",
        str(corpus),
        "--db",
        str(tmp_root / "cli-index.sqlite3"),
    ]


def test_index_then_query_reports_sources_and_exit_codes(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)

    indexed = run_cli(*args, "index")
    assert indexed.returncode == 0, indexed.stderr
    assert "chunks: created=" in indexed.stdout

    queried = run_cli(*args, "query", "review checklist", "--json")
    assert queried.returncode == 0, queried.stderr
    payload = json.loads(queried.stdout)
    assert payload["status"] == "ok"
    assert payload["method"] == "fts5"
    assert payload["index_version"].startswith("sha256:")
    assert payload["plan"]["terms"]
    for item in payload["results"]:
        assert item["source_path"] and item["source_url"] and item["license"]
        assert item["text_hash"].startswith("sha256:")
        assert item["rank"] >= 1


def test_query_without_index_exits_2(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    completed = run_cli(*args, "query", "review checklist")
    assert completed.returncode == 2
    assert "索引库不存在" in completed.stderr


def test_empty_query_exits_1_with_explicit_status(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    completed = run_cli(*args, "query", "   ", "--json")
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "empty"
    assert payload["reason"] == "empty_query"


def test_no_results_exits_1_and_never_fabricates(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    completed = run_cli(*args, "query", "zzzzz-nonexistent-token", "--json")
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "empty"
    assert payload["reason"] == "no_results"
    assert payload["results"] == []


def test_context_uses_decision_payload_as_authoritative_facts(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    completed = run_cli(
        *args, "context", "review checklist", "--decision", str(DECISION_FIXTURE)
    )
    assert completed.returncode == 0, completed.stderr
    stdout = completed.stdout
    assert stdout.index("[P1] ARCH-001@1") < stdout.index("[K1]")
    assert "不可信数据" in stdout
    assert "ENGINEERING-REFERENCE-BEGIN" in stdout


def test_context_rejects_unknown_decision_schema(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    payload = json.loads(DECISION_FIXTURE.read_text(encoding="utf-8"))
    payload["schema_version"] = "9.9"
    broken = tmp_root / "broken-decision.json"
    broken.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="")
    completed = run_cli(*args, "context", "review checklist", "--decision", str(broken))
    assert completed.returncode == 2
    assert "unknown" in completed.stderr.lower() or "未知" in completed.stderr


def test_verify_reports_hash_drift_and_exits_1(tmp_root: Path) -> None:
    corpus = write_fixture_corpus(tmp_root, drift=("guides/index.md",))
    completed = run_cli("--root", str(tmp_root), "--corpus", str(corpus), "verify", "--json")
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    kinds = [issue["kind"] for issue in payload["issues"]]
    assert "hash_mismatch" in kinds

    clean = write_fixture_corpus(tmp_root)
    completed_clean = run_cli(
        "--root", str(tmp_root), "--corpus", str(clean), "verify"
    )
    assert completed_clean.returncode == 0
    assert "OK" in completed_clean.stdout


def test_unknown_dataset_exits_2(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    completed = run_cli(*args, "query", "review", "--dataset", "nope")
    assert completed.returncode == 2
    assert "不存在的数据集" in completed.stderr


def test_rules_subcommand_shows_provenance(tmp_root: Path) -> None:
    corpus = write_fixture_corpus(
        tmp_root,
        rule_sources=[
            {
                "rule_id": "REVIEW-900",
                "rule_version": 1,
                "dataset": "guides",
                "source_path": "topics.md",
                "heading_path": ["Review Topics", "Tests"],
            }
        ],
    )
    args = base_args(tmp_root, corpus)
    run_cli(*args, "index")
    found = run_cli(*args, "rules", "--rule", "REVIEW-900", "--json")
    assert found.returncode == 0, found.stderr
    rows = json.loads(found.stdout)
    assert len(rows) == 1
    assert rows[0]["source_path"] == "topics.md"
    assert rows[0]["heading_path"] == ["Review Topics", "Tests"]

    missing = run_cli(*args, "rules", "--rule", "ARCH-001")
    assert missing.returncode == 1


def test_quarantine_and_release_roundtrip(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    found = json.loads(run_cli(*args, "query", "IGNORE ALL PREVIOUS INSTRUCTIONS", "--json").stdout)
    assert found["status"] == "ok"
    target = found["results"][0]["chunk_id"]

    quarantined = run_cli(*args, "quarantine", "--chunk", target, "--reason", "注入样本")
    assert quarantined.returncode == 0, quarantined.stderr
    after = json.loads(run_cli(*args, "query", "IGNORE ALL PREVIOUS INSTRUCTIONS", "--json").stdout)
    assert all(item["chunk_id"] != target for item in after.get("results", []))

    released = run_cli(*args, "quarantine", "--chunk", target, "--reason", "复核通过", "--release")
    assert released.returncode == 0, released.stderr
    restored = json.loads(run_cli(*args, "query", "IGNORE ALL PREVIOUS INSTRUCTIONS", "--json").stdout)
    assert any(item["chunk_id"] == target for item in restored["results"])


def test_index_check_reports_up_to_date(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    before = run_cli(*args, "index", "--check", "--json")
    assert before.returncode == 0
    assert json.loads(before.stdout)["needs_reindex"] is True
    run_cli(*args, "index")
    after = run_cli(*args, "index", "--check", "--json")
    assert json.loads(after.stdout)["needs_reindex"] is False


def test_real_corpus_end_to_end_via_cli(tmp_root: Path) -> None:
    """真实仓库语料：index -> verify -> query -> context 全链路（不依赖夹具）。"""

    db = tmp_root / "real-index.sqlite3"
    args = ["--db", str(db)]
    indexed = run_cli(*args, "index", "--json")
    assert indexed.returncode == 0, indexed.stderr
    report = json.loads(indexed.stdout)
    assert report["status"] == "completed"
    assert report["documents_indexed"] == 27
    assert report["chunks_created"] > 200

    verified = run_cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr

    queried = run_cli(
        *args, "query", "RAG 检索失败时是否可以让模型自己回答", "--json", "--limit", "3"
    )
    assert queried.returncode == 0, queried.stderr
    payload = json.loads(queried.stdout)
    assert payload["status"] == "ok"
    top_sources = [item["source_path"] for item in payload["results"]]
    assert any("RAG_Security_Cheat_Sheet.md" in item for item in top_sources)

    context = run_cli(*args, "context", "代码评审需要检查哪些方面", "--json", "--limit", "2")
    assert context.returncode == 0, context.stderr
    rendered = json.loads(context.stdout)
    assert rendered["status"] == "ok"
    assert rendered["used_chars"] <= rendered["budget_chars"]
    assert rendered["snippets"] and all(item["text_hash"] for item in rendered["snippets"])


def test_vector_build_and_query_via_cli(tmp_root: Path) -> None:
    db = tmp_root / "vector-index.sqlite3"
    args = ["--db", str(db)]
    assert run_cli(*args, "index").returncode == 0
    built = run_cli(*args, "vector", "--build")
    assert built.returncode == 0, built.stderr
    assert "built=" in built.stdout

    completed = run_cli(*args, "vector", "code review checklist", "--json", "--limit", "3")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["method"] == "vector"
    assert payload["status"] == "ok"
    assert payload["results"][0]["source_path"]


def test_manifest_dataset_is_reported_in_stats(tmp_root: Path, cli_project: Path) -> None:
    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    completed = run_cli(*args, "stats", "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["documents"] == 4
    assert payload["chunks"] > 0
    assert {name for name, _ in payload["datasets"]} == {
        "adversarial",
        "guides",
        "restricted-docs",
    }


def test_corrupted_index_reports_config_error_not_traceback(tmp_root: Path, cli_project: Path) -> None:
    """索引库文件损坏必须是"配置/执行错误"（退出码 2），不能是 traceback + 退出码 1。"""

    args = base_args(tmp_root, cli_project)
    run_cli(*args, "index")
    database = tmp_root / "cli-index.sqlite3"
    database.write_bytes(b"this is not a sqlite database" * 40)

    completed = run_cli(*args, "query", "review checklist")
    assert completed.returncode == 2
    assert "error" in completed.stderr and "Traceback" not in completed.stderr
    assert completed.stdout == ""


def test_index_budget_too_small_exits_2(tmp_root: Path) -> None:
    """Context 预算放不下必需内容时是配置错误（退出码 2），而不是"没有命中"（退出码 1）。"""

    corpus = write_fixture_corpus(tmp_root, policy={"context_budget_chars": 400, "max_snippet_chars": 200})
    args = base_args(tmp_root, corpus)
    run_cli(*args, "index")

    payload = json.loads(DECISION_FIXTURE.read_text(encoding="utf-8"))
    payload["violations"][0]["message"] = "超长规则说明" * 200
    decision = tmp_root / "long-decision.json"
    decision.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="")

    completed = run_cli(*args, "context", "review checklist", "--decision", str(decision))
    assert completed.returncode == 2
    assert "config error" in completed.stderr
    assert "预算" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_fixture_corpus_loads_without_expansion(tmp_root: Path, cli_project: Path) -> None:
    loaded = load_fixture_corpus(tmp_root)
    assert loaded.policy.expansion is None
