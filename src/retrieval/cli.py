"""retrieval 命令行入口。

用法：

    python -m retrieval.cli index    [--corpus knowledge/corpus.yaml] [--db .tmp/retrieval/index.sqlite3]
    python -m retrieval.cli query    "代码评审需要检查哪些方面" [--dataset ...] [--json]
    python -m retrieval.cli context  "..." [--decision <决策载荷.json>] [--json]
        # --decision 接的是真实存在的决策载荷：仓库快照（tests/fixtures/decisions/block.json）
        # 或先用 python -m policy.check ... --json > .tmp/decision.json 生成一份
    python -m retrieval.cli verify   [--json]
    python -m retrieval.cli stats    [--json]
    python -m retrieval.cli rules    (--rule ARCH-001 [--version 1] | --chunk chunk_...)
    python -m retrieval.cli quarantine --chunk chunk_... --reason "..."

退出码：

    0 = 成功（索引完成 / 有命中 / 校验通过 / Context 可用）
    1 = 明确的否定结果（无命中、知识不可用、校验发现问题、溯源查不到）
    2 = 配置或执行错误（清单不可读、索引库打不开、未知数据集、决策协议拒绝）

检索结果与 Context 默认输出人类可读文本，--json 时输出机器可读载荷。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from policy.models import ProtocolError, parse_decision

from .context import ContextBudgetError, ContextBuilder, render_context
from .corpus import CorpusError, load_corpus, load_expansion, verify_corpus
from .indexer import DEFAULT_CORPUS_PATH, IndexReport, ingest, needs_reindex, quarantine_chunk
from .models import (
    AccessScope,
    CorpusManifest,
    EngineeringContext,
    Operation,
    PolicyFact,
    RetrievalError,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStatus,
    Tier,
    UnavailableReason,
)
from .retriever import FtsRetriever, ResultCache
from .store import DEFAULT_DB_PATH, ChunkStore, StoreError
from .vector import VectorRetriever

__all__ = [
    "EXIT_ERROR",
    "EXIT_NEGATIVE",
    "EXIT_OK",
    "build_parser",
    "default_paths",
    "main",
    "render_index",
    "render_result",
    "repo_root",
    "run",
]

EXIT_OK = 0
EXIT_NEGATIVE = 1
EXIT_ERROR = 2


def repo_root() -> Path:
    """仓库根目录：从本模块位置向上回溯到含 knowledge/corpus.yaml 或 .git 的目录。"""

    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / DEFAULT_CORPUS_PATH).is_file() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def default_paths(root: Path) -> tuple[Path, Path]:
    return root / DEFAULT_CORPUS_PATH, root / DEFAULT_DB_PATH


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    # 公共参数同时挂在主解析器与每个子命令上，并且默认值用 SUPPRESS：
    # 子命令默认值不会覆盖写在子命令之前的同名参数（argparse 的子命令会把整个
    # 子命名空间拷回主命名空间，默认值会盖掉前面的显式取值）。
    common.add_argument(
        "--root",
        default=argparse.SUPPRESS,
        help="项目根目录（清单、镜像与相对路径的锚点）；默认自动探测仓库根",
    )
    common.add_argument(
        "--corpus", default=argparse.SUPPRESS, help=f"摄取清单，默认 {DEFAULT_CORPUS_PATH}"
    )
    common.add_argument(
        "--db", default=argparse.SUPPRESS, help=f"索引库路径，默认 {DEFAULT_DB_PATH}"
    )
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="输出机器可读结果"
    )

    parser = argparse.ArgumentParser(
        prog="python -m retrieval.cli",
        description="离线规范检索：摄取镜像文档、建立 FTS5 基线、组装带来源的 Engineering Context。",
        parents=[common],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    # 每个子命令都继承公共参数：--json / --root / --db 放在子命令前后都能用。
    subparsers.required = True

    index_parser = subparsers.add_parser("index", parents=[common], help="摄取并重建索引（幂等）")
    index_parser.add_argument(
        "--check", action="store_true", help="只检查是否需要重建，不写入索引库"
    )
    index_parser.add_argument("--run-id", default=None, help="覆盖 run id（便于重放对比）")

    query_parser = subparsers.add_parser("query", parents=[common], help="检索片段")
    query_parser.add_argument("text", help="任务描述（作为数据，不参与过滤条件构造）")
    _add_query_arguments(query_parser)

    context_parser = subparsers.add_parser("context", parents=[common], help="组装 Engineering Context")
    context_parser.add_argument("text", nargs="?", default=None, help="任务描述")
    _add_query_arguments(context_parser)
    context_parser.add_argument(
        "--decision",
        default=None,
        metavar="PATH",
        help="Phase 1 决策载荷（JSON 文件，或 - 表示 stdin）；只把 violations 变成策略事实",
    )
    context_parser.add_argument("--request-id", default=None)

    subparsers.add_parser("verify", parents=[common], help="校验清单、镜像 manifest、许可与哈希")
    subparsers.add_parser("stats", parents=[common], help="索引库统计")

    rules_parser = subparsers.add_parser("rules", parents=[common], help="查询规则的来源溯源")
    rules_parser.add_argument("--rule", default=None, help="规则 ID，例如 ARCH-001")
    rules_parser.add_argument("--version", type=int, default=None, help="规则版本")
    rules_parser.add_argument("--chunk", default=None, help="反向查询：某个 chunk 被哪些规则引用")

    quarantine_parser = subparsers.add_parser("quarantine", parents=[common], help="隔离一个已知恶意 chunk")
    quarantine_parser.add_argument("--chunk", required=True)
    quarantine_parser.add_argument("--reason", required=True)
    quarantine_parser.add_argument("--release", action="store_true", help="解除隔离")

    vector_parser = subparsers.add_parser("vector", parents=[common], help="向量检索（对照评测用）")
    vector_parser.add_argument("--build", action="store_true", help="建立/补齐向量")
    vector_parser.add_argument("text", nargs="?", default=None, help="查询文本（给出时直接检索）")
    _add_query_arguments(vector_parser)
    return parser


def _add_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", action="append", default=[], help="限定数据集，可重复")
    parser.add_argument("--tier", action="append", default=[], choices=[item.value for item in Tier])
    parser.add_argument("--language", default=None, help="上下文语言（软词项 + 过滤）")
    parser.add_argument("--module", default=None, help="模块名（软词项）")
    parser.add_argument("--file", default=None, help="仓库相对文件路径（软词项，取文件名主干）")
    parser.add_argument(
        "--operation", default=None, choices=[item.value for item in Operation]
    )
    parser.add_argument(
        "--subject", default="local-user", help="请求主体（只用于缓存键与审计，不改变权限集合）"
    )
    parser.add_argument("--limit", type=int, default=None, help="返回片段数上限")
    parser.add_argument(
        "--allow-restricted",
        action="store_true",
        help="显式允许检索 visibility=restricted 的数据集（默认关闭）",
    )


def _granted_datasets(manifest: CorpusManifest, requested: Sequence[str]) -> tuple[str, ...]:
    declared = set(manifest.dataset_names)
    if not requested:
        return manifest.dataset_names
    unknown = sorted(set(requested) - declared)
    if unknown:
        raise CorpusError(f"请求了清单里不存在的数据集 {unknown}；已声明的数据集为 {sorted(declared)}")
    return tuple(sorted(set(requested)))


def _scope(manifest: CorpusManifest, args: argparse.Namespace, *, datasets: Sequence[str]) -> AccessScope:
    return AccessScope(
        subject=args.subject,
        datasets=frozenset(_granted_datasets(manifest, datasets)),
        allow_restricted=bool(getattr(args, "allow_restricted", False)),
    )


def _retrieval_query(args: argparse.Namespace, *, text: Optional[str]) -> RetrievalQuery:
    return RetrievalQuery(
        text=text,
        file=args.file,
        language=args.language,
        module=args.module,
        operation=args.operation,
        datasets=tuple(args.dataset),
        tiers=tuple(args.tier),
        limit=args.limit,
        request_id=getattr(args, "request_id", None),
    )


def _open_store(path: Path, *, create: bool) -> ChunkStore:
    return ChunkStore(path, create=create)


def render_index(report: IndexReport) -> str:
    lines = [
        f"run: {report.run_id} [{report.status.value}] corpus={report.corpus}",
        f"index: {report.index_version} input={report.input_hash}",
        (
            "documents: indexed={0} removed={1} | chunks: created={2} updated={3} "
            "unchanged={4} removed={5}"
        ).format(
            report.documents_indexed,
            report.documents_removed,
            report.chunks_created,
            report.chunks_updated,
            report.chunks_unchanged,
            report.chunks_removed,
        ),
        (
            f"truncated={report.truncated_chunks} oversized={report.oversized_chunks} "
            f"empty_sections={report.empty_sections} quarantine={report.quarantined_chunks}"
        ),
    ]
    if report.released_quarantine:
        lines.append("released quarantine: " + ", ".join(report.released_quarantine))
    if report.rule_sources:
        lines.append(
            "rule sources: "
            + ", ".join(f"{rule}@{version}->{chunk}" for rule, version, chunk in report.rule_sources)
        )
    if report.drift:
        lines.append("integrity drift（镜像哈希与本地不一致，必须人工确认）:")
        for issue in report.drift:
            lines.append(f"  - {issue.dataset}:{issue.source_path} {issue.detail}")
    for outcome in report.documents:
        if outcome.front_matter_warning or outcome.hash_drift:
            lines.append(
                f"  ! {outcome.dataset}:{outcome.source_path} "
                f"{outcome.front_matter_warning or ''} {'hash_drift' if outcome.hash_drift else ''}".strip()
            )
    return chr(10).join(lines)


def render_result(result: RetrievalResult) -> str:
    lines = [
        f"query: {result.query}",
        f"status: {result.status.value}"
        + (f" ({result.reason.value})" if result.reason is not None else ""),
        f"index: {result.index_version} | method: {result.method.value}",
    ]
    if result.plan is not None:
        lines.append("terms: " + " | ".join(result.plan.terms[:12]))
    for hit in result.results:
        heading = " > ".join(hit.heading_path) or "<root>"
        lines.append(
            f"  {hit.rank}. [{hit.score:.3f}] {hit.source_path}#{hit.heading_anchor} "
            f"({hit.dataset}/{hit.tier.value}) {heading}"
        )
        lines.append("     " + hit.text.strip().split(chr(10))[0][:120])
    return chr(10).join(lines)


def render_context_text(context: EngineeringContext) -> str:
    return render_context(context)


def _decision_facts(path: str) -> tuple[PolicyFact, ...]:
    """从 Phase 1 决策载荷里取违规作为策略事实；协议不认识就拒绝（不降级）。

    读不到文件、不是 JSON、协议版本不认识都按**配置错误**处理（退出码 2）：
    它是调用方给错参数，不该以裸 traceback 结束，也不是"没有策略事实"。
    """

    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise CorpusError(f"决策载荷读不到：{path}（{error}）") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CorpusError(f"决策载荷不是合法 JSON：{path}（{error}）") from error
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        payload = payload["result"]
    decision = parse_decision(payload)  # 未知 schema_version / 字段错误 -> ProtocolError
    facts: dict[str, PolicyFact] = {}
    for violation in decision.violations:
        identity = violation.canonical_id
        facts[identity] = PolicyFact(
            rule_id=identity,
            severity=violation.severity.value,
            message=violation.message,
            source_path=violation.evidence.file,
        )
    return tuple(facts[key] for key in sorted(facts))


def run(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))
    requested_root = getattr(args, "root", None)
    requested_corpus = getattr(args, "corpus", None)
    requested_db = getattr(args, "db", None)
    anchor = (
        root if root is not None else (Path(requested_root).resolve() if requested_root else repo_root())
    )
    default_corpus, default_db = default_paths(anchor)
    corpus_path = Path(requested_corpus) if requested_corpus else default_corpus
    db_path = Path(requested_db) if requested_db else default_db
    if requested_root and not requested_corpus:
        print(
            "config error: 指定 --root 时必须同时给出 --corpus（锚点变了，默认清单不再适用）",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        loaded = load_corpus(corpus_path, repo_root=anchor)
    except CorpusError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR

    if args.command == "verify":
        report = verify_corpus(loaded, repo_root=anchor)
        payload = {
            "corpus": report.corpus_path,
            "version": report.corpus_version,
            "datasets": report.datasets,
            "entries": report.entries,
            "ok": report.ok,
            "issues": [issue.model_dump() for issue in report.issues],
        }
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"corpus: {report.corpus_path} v{report.corpus_version} | "
                f"datasets={report.datasets} entries={report.entries} | "
                f"{'OK' if report.ok else 'ISSUES'}"
            )
            for issue in report.issues:
                print(f"  ! [{issue.kind}] {issue.dataset}:{issue.source_path} {issue.detail}")
        return EXIT_OK if report.ok else EXIT_NEGATIVE

    try:
        store = _open_store(db_path, create=args.command == "index")
    except StoreError as error:
        print(f"store error: {error}", file=sys.stderr)
        return EXIT_ERROR

    try:
        return _dispatch(args, loaded=loaded, store=store, anchor=anchor, as_json=as_json)
    finally:
        store.close()


def _dispatch(
    args: argparse.Namespace, *, loaded: Any, store: ChunkStore, anchor: Path, as_json: bool
) -> int:
    lexicon = (
        load_expansion(loaded.policy.expansion, repo_root=anchor)
        if loaded.policy.expansion
        else None
    )
    if args.command == "index":
        if args.check:
            needed = needs_reindex(loaded, store)
            payload = {
                "needs_reindex": needed,
                "input_hash": loaded.input_hash,
                "indexed_input_hash": store.corpus_input_hash,
                "index_version": store.index_version,
            }
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    "rebuild needed" if needed else "index is up to date for this corpus input"
                )
            return EXIT_OK
        report = ingest(loaded, store, repo_root=anchor, run_id=args.run_id)
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2, sort_keys=True) if as_json else render_index(report))
        return EXIT_OK

    if args.command == "stats":
        stats = store.stats()
        payload = stats.model_dump()
        payload["last_run"] = None if stats.last_run is None else stats.last_run.model_dump()
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        else:
            print(
                f"documents={stats.documents} chunks={stats.chunks} "
                f"quarantined={stats.quarantined} truncated={stats.truncated_chunks} "
                f"oversized={stats.oversized_chunks} embedded={stats.embedded_chunks}"
            )
            print(f"index_version={stats.index_version} generation={stats.generation}")
            for name, count in stats.datasets:
                print(f"  {name}: {count} documents")
        return EXIT_OK

    if args.command == "rules":
        if args.chunk:
            rows = store.rules_for_chunk(args.chunk)
            if as_json:
                print(json.dumps({"chunk_id": args.chunk, "rules": rows}, ensure_ascii=False, indent=2))
            else:
                print(f"chunk {args.chunk}: " + (", ".join(f"{r}@{v}" for r, v in rows) or "<none>"))
            return EXIT_OK if rows else EXIT_NEGATIVE
        if not args.rule:
            print("config error: rules 需要 --rule 或 --chunk", file=sys.stderr)
            return EXIT_ERROR
        rows = store.rule_sources(rule_id=args.rule.upper(), rule_version=args.version)
        payload = [row.model_dump() for row in rows]
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(
                    f"{row.rule_id}@{row.rule_version} <- {row.source_path}#{row.heading_anchor} "
                    f"({row.chunk_id})"
                )
            if not rows:
                print(f"{args.rule}: 没有登记的来源溯源")
        return EXIT_OK if rows else EXIT_NEGATIVE

    if args.command == "quarantine":
        try:
            if args.release:
                released = store.release_quarantine(args.chunk)
                print(("released " if released else "not quarantined ") + args.chunk)
                return EXIT_OK if released else EXIT_NEGATIVE
            stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            text_hash = quarantine_chunk(
                store, chunk_id=args.chunk, reason=args.reason, quarantined_at=stamp
            )
            print(f"quarantined {args.chunk} (text_hash={text_hash})")
            return EXIT_OK
        except Exception as error:  # noqa: BLE001 - CLI 边界：任何失败都给出可诊断信息
            print(f"quarantine error: {error}", file=sys.stderr)
            return EXIT_ERROR

    if args.command == "vector":
        retriever = VectorRetriever(store, policy=loaded.policy, lexicon=lexicon)
        built = retriever.build() if args.build else 0
        if args.text is None:
            metadata = store.embedding_metadata()
            print(f"built={built} embeddings={metadata}")
            return EXIT_OK

    try:
        scope = _scope(loaded.manifest, args, datasets=args.dataset)
    except CorpusError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR

    try:
        if args.command == "context":
            facts: tuple[PolicyFact, ...] = ()
            if args.decision:
                facts = _decision_facts(args.decision)
            retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon)
            result = (
                None
                if args.text is None and not facts
                else retriever.retrieve(_retrieval_query(args, text=args.text), scope)
            )
            builder = ContextBuilder.from_policy(loaded.policy)
            context = builder.build(
                retrieval=result,
                policy_facts=facts,
                query=args.text or "",
                request_id=args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
                unavailable_reason=None if result is not None else UnavailableReason.EMPTY_QUERY,
            )
            if as_json:
                print(json.dumps(context.model_dump(), ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(render_context(context))
            return EXIT_OK if context.status.value == "ok" else EXIT_NEGATIVE

        if args.command == "vector":
            retriever = VectorRetriever(store, policy=loaded.policy, lexicon=lexicon)
            result = retriever.retrieve(_retrieval_query(args, text=args.text), scope)
        else:
            retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=ResultCache())
            result = retriever.retrieve(_retrieval_query(args, text=args.text), scope)
    except ContextBudgetError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except (CorpusError, ProtocolError, StoreError, RetrievalError) as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except json.JSONDecodeError as error:
        print(f"config error: 决策载荷不是合法 JSON ({error})", file=sys.stderr)
        return EXIT_ERROR

    if as_json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_result(result))
    return EXIT_OK if result.status is RetrievalStatus.OK else EXIT_NEGATIVE


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
