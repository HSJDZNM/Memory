"""摄取清单加载、镜像 manifest 对齐与完整性校验。

清单是数据（knowledge/corpus.yaml），本模块只做三件事：

1. 把 YAML 解析成受控模型（未知字段、缺许可、缺 mirror 一律报错，不静默忽略）；
2. 与镜像自带的 manifest.json 对齐：来源 URL、标题、sha256、字节数、抓取时间都从那里取，
   不允许在清单里手抄（手抄就会漂移）；
3. 给出可重放的完整性报告：文件缺失、哈希漂移、许可声明文件不存在、条目未标记保存。

哈希漂移的语义：镜像 manifest 记录的 sha256 与本地文件哈希不一致，说明本地内容在上游记录
之外被改过。**不静默**——写进 document 行的 manifest_hash/content_hash，进 run 报告，
并让 verify 以退出码 1 报出来；但摄取本身继续（合法的重爬会先更新 manifest 再更新文件）。
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Tuple

import yaml
from pydantic import ValidationError

from .models import (
    CorpusDataset,
    CorpusError,
    CorpusManifest,
    ResolvedEntry,
    StrictModel,
    sha256_text,
)

__all__ = [
    "CorpusVerification",
    "EntryIssue",
    "ExpansionLexicon",
    "ExpansionTerm",
    "LoadedCorpus",
    "load_corpus",
    "load_expansion",
    "read_mirror_manifest",
    "verify_corpus",
]

_MANIFEST_NAME = "manifest.json"
_MAX_ZH_CHARS = 10
_MAX_EN_WORDS = 4


class EntryIssue(StrictModel):
    """一条完整性问题。kind 是受控取值，便于测试与 CLI 稳定输出。"""

    dataset: str
    source_path: str
    kind: str
    detail: str


class CorpusVerification(StrictModel):
    """清单与镜像、文件系统的一致性报告。"""

    corpus_path: str
    corpus_version: int
    datasets: int
    entries: int
    issues: Tuple[EntryIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def drift(self) -> Tuple[EntryIssue, ...]:
        return tuple(issue for issue in self.issues if issue.kind == "hash_mismatch")


class LoadedCorpus(StrictModel):
    """一次加载的完整结果：清单 + 已解析条目 + 完整性报告。"""

    manifest: CorpusManifest
    entries: Tuple[ResolvedEntry, ...]
    verification: CorpusVerification
    corpus_path: str

    @property
    def policy(self):
        return self.manifest.policy

    def entry(self, dataset: str, source_path: str) -> ResolvedEntry:
        for item in self.entries:
            if item.dataset == dataset and item.source_path == source_path:
                return item
        raise CorpusError(f"清单里没有这个入口：{dataset}:{source_path}")

    def dataset(self, name: str) -> CorpusDataset:
        return self.manifest.dataset(name)

    @property
    def input_hash(self) -> str:
        """摄取输入指纹：清单内容 + 每个条目的镜像哈希 + 分块与扩展资产版本。"""

        payload = [
            f"corpus:{self.corpus_path}:v{self.manifest.version}",
            "policy:" + self.manifest.policy.model_dump_json(),
        ]
        for item in sorted(self.entries, key=lambda entry: (entry.dataset, entry.source_path)):
            payload.append(
                "|".join(
                    [
                        item.dataset,
                        item.source_path,
                        item.manifest_sha256 or "<no-manifest-hash>",
                        item.tier.value,
                        item.visibility.value,
                        item.language or "<no-language>",
                        item.license,
                    ]
                )
            )
        return sha256_text(chr(10).join(payload))


def _read_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CorpusError(f"{path}: 无法读取摄取清单 ({error})") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise CorpusError(f"{path}: 摄取清单 YAML 解析失败 -> {error}") from error
    if document is None:
        raise CorpusError(f"{path}: 摄取清单为空")
    if not isinstance(document, Mapping):
        raise CorpusError(f"{path}: 摄取清单顶层必须是映射，得到 {type(document).__name__}")
    return document


def read_mirror_manifest(mirror_root: Path) -> Mapping[str, Any]:
    """读取镜像的 manifest.json；缺失或结构不对都属于配置错误（不猜内容）。"""

    path = mirror_root / _MANIFEST_NAME
    if not path.is_file():
        raise CorpusError(f"镜像目录缺少 {_MANIFEST_NAME}: {mirror_root}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CorpusError(f"{path}: 镜像 manifest 不可解析 ({error})") from error
    if not isinstance(document, Mapping) or not isinstance(document.get("pages"), list):
        raise CorpusError(f"{path}: 镜像 manifest 缺少 pages 列表")
    return document


def _pages_by_path(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    pages: dict[str, Mapping[str, Any]] = {}
    for page in document.get("pages", []):
        if not isinstance(page, Mapping):
            continue
        local = page.get("local_path")
        if isinstance(local, str):
            pages[local] = page
    return pages


def _resolve_dataset(
    dataset: CorpusDataset, *, repo_root: Path
) -> Tuple[Tuple[ResolvedEntry, ...], Tuple[EntryIssue, ...]]:
    mirror_root = repo_root / dataset.mirror
    if not mirror_root.is_dir():
        raise CorpusError(f"数据集 {dataset.name} 的镜像目录不存在: {dataset.mirror}")
    document = read_mirror_manifest(mirror_root)
    pages = _pages_by_path(document)
    revision = document.get("fetched_at")
    revision_text = revision if isinstance(revision, str) else None

    resolved: list[ResolvedEntry] = []
    issues: list[EntryIssue] = []
    for source_path in dataset.entries:
        page = pages.get(source_path)
        if page is None:
            raise CorpusError(
                f"数据集 {dataset.name} 的条目不在镜像 manifest 中: {source_path}"
                "（清单只能引用镜像里真实存在的页面）"
            )
        if page.get("saved") is False:
            issues.append(
                EntryIssue(
                    dataset=dataset.name,
                    source_path=source_path,
                    kind="not_saved",
                    detail="镜像 manifest 把该页标记为 saved=false",
                )
            )
        url = page.get("source_url")
        title = page.get("title")
        if not isinstance(url, str) or not url.strip():
            raise CorpusError(f"{dataset.name}:{source_path} 的镜像 manifest 缺少 source_url")
        resolved.append(
            ResolvedEntry(
                dataset=dataset.name,
                source_path=source_path,
                title=str(title) if title else PurePosixPath(source_path).stem,
                source_url=url.strip(),
                license=dataset.license,
                license_source=dataset.license_source,
                tier=dataset.tier,
                visibility=dataset.visibility,
                language=dataset.language,
                manifest_sha256=_string_or_none(page.get("sha256")),
                manifest_bytes=_int_or_none(page.get("bytes")),
                mirror_revision=revision_text,
            )
        )
    return tuple(resolved), tuple(issues)


def _string_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) else None


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def verify_corpus(loaded: LoadedCorpus, *, repo_root: Path) -> CorpusVerification:
    """对已加载的清单做完整性检查：文件、哈希、许可声明、镜像目录。"""

    issues: list[EntryIssue] = list(loaded.verification.issues)
    mirrors = {dataset.name: dataset.mirror for dataset in loaded.manifest.datasets}
    for item in loaded.entries:
        mirror = mirrors.get(item.dataset)
        if mirror is None:
            raise CorpusError(f"入口引用了未声明的数据集: {item.dataset}")
        relative = f"{mirror}/{item.source_path}"
        path = repo_root / relative
        if not path.is_file():
            issues.append(
                EntryIssue(
                    dataset=item.dataset,
                    source_path=item.source_path,
                    kind="missing_file",
                    detail=f"文件不存在: {relative}",
                )
            )
            continue
        observed = _file_hash(path)
        if item.manifest_sha256 is not None and observed != item.manifest_sha256:
            issues.append(
                EntryIssue(
                    dataset=item.dataset,
                    source_path=item.source_path,
                    kind="hash_mismatch",
                    detail=f"镜像 manifest={item.manifest_sha256} 本地={observed}",
                )
            )
        if item.manifest_bytes is not None and item.manifest_bytes != path.stat().st_size:
            issues.append(
                EntryIssue(
                    dataset=item.dataset,
                    source_path=item.source_path,
                    kind="size_mismatch",
                    detail=f"镜像 manifest={item.manifest_bytes} 本地={path.stat().st_size}",
                )
            )
    for dataset in loaded.manifest.datasets:
        if dataset.license_source is not None and not (repo_root / dataset.license_source).is_file():
            issues.append(
                EntryIssue(
                    dataset=dataset.name,
                    source_path=dataset.license_source,
                    kind="license_source_missing",
                    detail="清单声明的许可声明文件不存在",
                )
            )
    return loaded.verification.model_copy(update={"issues": tuple(issues)})


def load_corpus(
    path: Path | str, *, repo_root: Path | str
) -> LoadedCorpus:
    """加载摄取清单并解析全部条目；无法解析的条目直接失败（不猜、不跳过）。"""

    root = Path(repo_root).resolve()
    corpus_path = Path(path)
    if not corpus_path.is_absolute():
        corpus_path = root / corpus_path
    if not corpus_path.is_file():
        raise CorpusError(f"摄取清单不存在: {corpus_path}")

    document = _read_yaml_mapping(corpus_path)
    try:
        manifest = CorpusManifest.model_validate(document)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item.get('loc', ())) or '<root>'}: {item.get('msg')}"
            for item in error.errors()
        )
        raise CorpusError(f"{corpus_path}: 摄取清单校验失败 -> {details}") from error
    if not manifest.datasets:
        raise CorpusError(f"{corpus_path}: 摄取清单没有任何数据集")

    entries: list[ResolvedEntry] = []
    issues: list[EntryIssue] = []
    for dataset in manifest.datasets:
        dataset_entries, dataset_issues = _resolve_dataset(dataset, repo_root=root)
        entries.extend(dataset_entries)
        issues.extend(dataset_issues)

    relative = corpus_path.relative_to(root).as_posix() if corpus_path.is_relative_to(root) else str(corpus_path)
    verification = CorpusVerification(
        corpus_path=relative,
        corpus_version=manifest.version,
        datasets=len(manifest.datasets),
        entries=len(entries),
        issues=tuple(issues),
    )
    loaded = LoadedCorpus(
        manifest=manifest,
        entries=tuple(sorted(entries, key=lambda item: (item.dataset, item.source_path))),
        verification=verification,
        corpus_path=relative,
    )
    return loaded.model_copy(update={"verification": verify_corpus(loaded, repo_root=root)})


class ExpansionTerm(StrictModel):
    """一条术语映射：中文术语（若干写法）→ 上游文档使用的英文术语。"""

    zh: Tuple[str, ...] = ()
    en: Tuple[str, ...] = ()

    @property
    def max_zh_length(self) -> int:
        return max((len(item) for item in self.zh), default=0)


class ExpansionLexicon(StrictModel):
    """受控术语表。它只做跨语言的词法桥接，不引入任何"答案"。"""

    version: int = 1
    terms: Tuple[ExpansionTerm, ...] = ()

    @property
    def _index(self) -> dict[str, Tuple[str, ...]]:
        table: dict[str, Tuple[str, ...]] = {}
        for term in self.terms:
            for key in term.zh:
                table[key] = term.en
        return table

    def expand(self, text: str) -> Tuple[str, ...]:
        """最长匹配扩展：同一段文本里"代码评审"优先于"评审"。"""

        if not text:
            return ()
        table = self._index
        matches: list[Tuple[int, int, str]] = []
        for key in table:
            start = text.find(key)
            while start != -1:
                matches.append((start, start + len(key), key))
                start = text.find(key, start + 1)
        matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        taken: list[Tuple[int, int]] = []
        expansions: list[str] = []
        for start, end, key in matches:
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            taken.append((start, end))
            expansions.extend(table[key])
        ordered: list[str] = []
        for item in expansions:
            if item not in ordered:
                ordered.append(item)
        return tuple(ordered)


def load_expansion(path: Path | str, *, repo_root: Path | str) -> ExpansionLexicon:
    """加载术语表；句子、标点、超长条目一律报错（它不是评测集的逆向工程）。"""

    root = Path(repo_root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    if not target.is_file():
        raise CorpusError(f"术语表不存在: {target}")
    document = _read_yaml_mapping(target)
    try:
        lexicon = ExpansionLexicon.model_validate(document)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item.get('loc', ())) or '<root>'}: {item.get('msg')}"
            for item in error.errors()
        )
        raise CorpusError(f"{target}: 术语表校验失败 -> {details}") from error

    seen: dict[str, str] = {}
    for term in lexicon.terms:
        if not term.zh or not term.en:
            raise CorpusError(f"{target}: 术语条目必须同时声明 zh 与 en")
        for key in term.zh:
            if len(key) > _MAX_ZH_CHARS or key != key.strip() or len(key.split()) > 2:
                raise CorpusError(
                    f"{target}: 术语必须是单个术语（不超过 {_MAX_ZH_CHARS} 字、最多两段）：{key!r}"
                )
            if any(char in key for char in "，。？！！,.;:：；、（）()"):
                raise CorpusError(f"{target}: 中文术语不能包含标点：{key!r}")
            if key in seen:
                raise CorpusError(f"{target}: 中文术语重复登记：{key!r}")
            seen[key] = key
        for item in term.en:
            if not item.strip() or len(item.split()) > _MAX_EN_WORDS:
                raise CorpusError(
                    f"{target}: 英文术语必须是不超过 {_MAX_EN_WORDS} 个词的短语：{item!r}"
                )
    return lexicon
