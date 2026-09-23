"""Phase 3 检索层的不可变模型与受控枚举。

边界（与 src/policy 同一套约定）：

- 只做类型、枚举与结构校验：不读文件、不连数据库、不调用 LLM；
- 所有模型 extra="forbid"、frozen=True：未知字段报错而不是静默忽略；
- 未知数据集、未知 tier、未知可见性、未知状态一律报错，不降级为"默认放行"；
- 检索结果只携带**来源与哈希**，相似度分数只用于内部排序，绝不作为授权信号；
- 检索层不导入任何 Agent SDK / Web 框架 / 向量库：向量检索是可替换端口（vector.py）。

ID 稳定性：document_id 只取决于 (dataset, source_path)，chunk_id 只取决于
(document_id, section_anchor, part_index)。因此重建索引后同一段原文仍是同一个 ID，
内容变化只会改变它自己的 text_hash —— 这是"只替换相关 chunk"和"可比较来源"的前提。
"""

from __future__ import annotations

import re
from enum import Enum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, FrozenSet, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from policy.models import Operation, PolicyContext, canonical_identifier, normalize_repo_path

__all__ = [
    "CHUNKER_VERSION",
    "DEFAULT_QUERY_TEXT_FIELDS",
    "INDEX_SCHEMA_VERSION",
    "AccessScope",
    "ChunkChange",
    "ChunkDraft",
    "ChunkKind",
    "ChunkRecord",
    "ContextSnippet",
    "ContextStatus",
    "CorpusDataset",
    "CorpusEntry",
    "CorpusError",
    "CorpusPolicy",
    "CorpusQuarantine",
    "CorpusRuleSource",
    "DroppedSnippet",
    "EngineeringContext",
    "IndexRunRecord",
    "IndexRunStatus",
    "IndexingError",
    "LayeredChunk",
    "ManifestUnavailableError",
    "PolicyFact",
    "QueryError",
    "QueryFilters",
    "QueryPlan",
    "QuarantinedChunk",
    "ResolvedEntry",
    "RetrievalError",
    "RetrievalMethod",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalStatus",
    "RetrievalUnavailableError",
    "RetrievedChunk",
    "StoreError",
    "Tier",
    "UnavailableReason",
    "Visibility",
    "chunk_id_for",
    "document_id_for",
    "normalize_dataset_name",
    "normalize_source_path",
    "sha256_text",
    "tier_priority",
]

# 索引结构版本：SQLite schema 或分块语义变化时必须递增，旧库直接拒绝打开。
INDEX_SCHEMA_VERSION = "1"
# 分块器版本：参与 document 的"是否需要重新分块"判断，改动分块语义必须递增。
CHUNKER_VERSION = "markdown-sections-2"

# 自由文本字段与结构化提示：检索查询由受控字段构造，绝不把原始用户输入直接拼进 SQL / FTS。
DEFAULT_QUERY_TEXT_FIELDS: Tuple[str, ...] = ("task",)


def sha256_text(value: str) -> str:
    """文本哈希，统一带 sha256: 前缀，便于与规则集哈希并列展示。"""

    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def document_id_for(dataset: str, source_path: str) -> str:
    """文档身份只取决于 (dataset, source_path)：重爬不换 ID，换了数据集就是另一份文档。"""

    payload = f"{canonical_identifier(dataset)}|{source_path}"
    return "doc_" + sha256(payload.encode("utf-8")).hexdigest()[:20]


def chunk_id_for(document_id: str, anchor: str, part_index: int) -> str:
    """chunk 身份只取决于 (document_id, 章节锚点, 片段序号)：与标题路径稳定对应。"""

    payload = f"{document_id}|{anchor}|{part_index}"
    return "chunk_" + sha256(payload.encode("utf-8")).hexdigest()[:24]


class RetrievalError(Exception):
    """检索层错误的基类。所有失败都必须带可诊断原因，不允许静默降级。"""


class CorpusError(RetrievalError):
    """摄取清单不可用或不合法（缺许可、缺 manifest、条目越界等）。"""


class IndexingError(RetrievalError):
    """索引进程失败；中断的 run 绝不能被标记为成功。"""


class StoreError(RetrievalError):
    """索引库不可用或结构版本不认识。"""


class ManifestUnavailableError(StoreError):
    """索引库不存在或不可读：调用方必须按"知识不可用"处理，不得回退到模型记忆。"""


class QueryError(RetrievalError):
    """查询无法规范化（空查询、非法字段、超长且无法截断）。"""


class RetrievalUnavailableError(RetrievalError):
    """检索不可用（库损坏、查询执行失败）。失败策略：不回退到无来源的答案。"""


class Tier(str, Enum):
    """三层规范模型的层级：Project Policy > Curated Guidance > Raw Reference。

    tier 只决定 Context 中的优先级，不决定授权。Policy 层级的片段同样只是"资料"，
    真正的授权永远由 Policy Engine 决定。
    """

    POLICY = "policy"
    GUIDANCE = "guidance"
    REFERENCE = "reference"


_TIER_PRIORITY: Mapping[Tier, int] = {Tier.POLICY: 0, Tier.GUIDANCE: 1, Tier.REFERENCE: 2}


def tier_priority(tier: Tier) -> int:
    """排序优先级：数字越小越靠前。仅用于解释与排序，不参与任何授权判断。"""

    return _TIER_PRIORITY[tier]


class Visibility(str, Enum):
    """数据集可见性。restricted 的数据集必须由调用方在 AccessScope 中显式授予。"""

    PUBLIC = "public"
    RESTRICTED = "restricted"


class ChunkKind(str, Enum):
    """chunk 的形态：纯段落、代码块，或两者混合。"""

    PROSE = "prose"
    CODE = "code"
    MIXED = "mixed"


class RetrievalMethod(str, Enum):
    """检索方式。方法名进结果与审计，方便比较 FTS5 基线与其他实现。"""

    FTS5 = "fts5"
    VECTOR = "vector"


class RetrievalStatus(str, Enum):
    """检索结果状态：ok（有结果）/ empty（查询合法但没有命中）/ unavailable（检索不可用）。"""

    OK = "ok"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"


class UnavailableReason(str, Enum):
    """"知识不可用"的具体原因，供上层决定如何失败关闭。"""

    EMPTY_QUERY = "empty_query"
    NO_RESULTS = "no_results"
    INDEX_MISSING = "index_missing"
    RETRIEVAL_FAILED = "retrieval_failed"
    ACCESS_DENIED = "access_denied"


class ContextStatus(str, Enum):
    """Engineering Context 状态：没有可追溯来源时必须是 knowledge_unavailable。"""

    OK = "ok"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"


class IndexRunStatus(str, Enum):
    """索引 run 状态。running 只表示进程还活着；被中断的 run 不能冒充成功。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class StrictModel(BaseModel):
    """检索层模型基类：拒绝未知字段、禁止创建后修改。"""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=False)


_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_CONTROL_CHARS = tuple(chr(code) for code in range(0, 32)) + (chr(127),)


def normalize_source_path(value: str) -> str:
    """规范化**镜像文档**路径：反斜杠转 "/"、去 "./" 与多余分隔符。

    这里与 policy.models.normalize_repo_path 都允许非 ASCII 段（OWASP 镜像用中文分类目录，
    仓库的架构文档目录同样是中文名），两边都不再要求 ASCII。
    差别只剩一处：policy 层额外拒绝路径元字符（Windows 文件名里不允许的 : * ? " < > |），
    因为规则来源与 PolicyContext.file 必须真的能表示仓库里的一个文件。
    两边都拒绝绝对路径、控制字符与 ".." 逃逸。
    """

    if not isinstance(value, str):
        raise CorpusError(f"路径必须是字符串，得到 {type(value).__name__}")
    raw = value.strip()
    if not raw:
        raise CorpusError("路径不能为空")
    candidate = raw.replace("\\", "/")
    if candidate.startswith("/") or _DRIVE_PREFIX_RE.match(candidate):
        raise CorpusError(f"路径必须是镜像内的相对路径: {raw!r}")
    if any(char in candidate for char in _CONTROL_CHARS):
        raise CorpusError(f"路径包含控制字符: {raw!r}")

    segments: list[str] = []
    for segment in candidate.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise CorpusError(f"路径逃出镜像根目录，拒绝处理: {raw!r}")
        segments.append(segment)
    if not segments:
        raise CorpusError(f"路径必须指向镜像内的文件: {raw!r}")
    return "/".join(segments)


def normalize_dataset_name(value: str) -> str:
    """数据集名规范化：小写 + 去空白，与规则作用域用同一口径。"""

    if not isinstance(value, str):
        raise CorpusError(f"数据集名必须是字符串，得到 {type(value).__name__}")
    normalized = canonical_identifier(value)
    if not normalized or not all(char.isalnum() or char in "._-" for char in normalized):
        raise CorpusError(f"数据集名只能是字母/数字/._-，得到 {value!r}")
    return normalized


def _normalize_path_list(values: Any, *, field: str) -> Any:
    if not isinstance(values, (list, tuple)):
        return values
    return tuple(normalize_repo_path(str(item)) for item in values)


class CorpusPolicy(StrictModel):
    """检索策略：预算与阈值写在清单里，代码中不留脱离数据的常数。"""

    top_k: int = Field(default=5, ge=1, le=50)
    max_query_chars: int = Field(default=200, ge=8, le=2000)
    max_query_terms: int = Field(default=24, ge=1, le=64)
    max_chunk_chars: int = Field(default=1200, ge=200, le=20000)
    hard_max_chunk_chars: int = Field(default=8000, ge=400, le=100000)
    context_budget_chars: int = Field(default=4000, ge=400, le=100000)
    max_snippet_chars: int = Field(default=1000, ge=200, le=20000)
    max_snippets: int = Field(default=8, ge=1, le=50)
    expansion: Optional[str] = "knowledge/query_expansion.yaml"
    vector_min_similarity: float = Field(
        default=0.25,
        ge=-1.0,
        le=1.0,
        description=(
            "向量检索的相关性下限：低于它的候选视为没有结果（EMPTY/NO_RESULTS）。"
            "取值来自实测分布（hashing-char3gram-256：无意义查询的相似度上限约 0.21，"
            "真实查询 0.29 起），而不是拍脑袋；换 embedding 必须重测并用同一评测集复评。"
        ),
    )

    @model_validator(mode="after")
    def _budgets_are_ordered(self) -> "CorpusPolicy":
        if self.max_chunk_chars > self.hard_max_chunk_chars:
            raise ValueError("max_chunk_chars 不能大于 hard_max_chunk_chars")
        if self.max_snippet_chars > self.context_budget_chars:
            raise ValueError("max_snippet_chars 不能大于 context_budget_chars")
        return self

    @field_validator("expansion")
    @classmethod
    def _check_expansion(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_source_path(value)


class CorpusEntry(StrictModel):
    """清单里的一条入口：镜像目录内的 Markdown 文件。"""

    source_path: str

    @field_validator("source_path")
    @classmethod
    def _check_source_path(cls, value: str) -> str:
        normalized = normalize_source_path(value)
        if PurePosixPath(normalized).suffix.lower() not in (".md", ".markdown"):
            raise ValueError(f"入口必须是 Markdown 文件，得到 {value!r}")
        return normalized


class CorpusDataset(StrictModel):
    """一个数据集 = 一个离线镜像目录 + 明确许可 + 明确的层级与可见性。"""

    name: str
    title: str = Field(min_length=1)
    mirror: str
    license: str = Field(min_length=1, description="许可标识；缺失即加载失败")
    license_source: Optional[str] = Field(
        default=None, description="许可声明所在的仓库相对路径，便于人工核对"
    )
    tier: Tier = Tier.GUIDANCE
    visibility: Visibility = Visibility.PUBLIC
    language: Optional[str] = Field(default=None, description="数据集的语言标签，可为 null")
    entries: Tuple[str, ...] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return normalize_dataset_name(value)

    @field_validator("mirror")
    @classmethod
    def _check_mirror(cls, value: str) -> str:
        return normalize_source_path(value)

    @field_validator("license_source")
    @classmethod
    def _check_license_source(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_source_path(value)

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("language 不能是空字符串；不知道就写 null")
        return normalized

    @field_validator("entries")
    @classmethod
    def _check_entries(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            path = normalize_source_path(item)
            if PurePosixPath(path).suffix.lower() not in (".md", ".markdown"):
                raise ValueError(f"入口必须是 Markdown 文件，得到 {item!r}")
            if path in seen:
                raise ValueError(f"数据集内入口重复：{path}")
            seen.add(path)
            normalized.append(path)
        return tuple(sorted(normalized))


class CorpusQuarantine(StrictModel):
    """已知恶意 chunk 的隔离登记：必须带 text_hash，源文一变旧隔离自动失效。"""

    chunk_id: str
    text_hash: str
    reason: str = Field(min_length=1)

    @field_validator("text_hash")
    @classmethod
    def _check_hash(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("sha256:") or len(normalized) != len("sha256:") + 64:
            raise ValueError(f"text_hash 必须是 sha256:<64 hex>，得到 {value!r}")
        return normalized


class CorpusRuleSource(StrictModel):
    """curated guidance → project policy 的溯源登记（rules(id, version, source_chunk_id)）。"""

    rule_id: str = Field(min_length=1)
    rule_version: int = Field(ge=1)
    dataset: str
    source_path: str
    heading_path: Tuple[str, ...] = ()

    @field_validator("dataset")
    @classmethod
    def _check_dataset(cls, value: str) -> str:
        return normalize_dataset_name(value)

    @field_validator("source_path")
    @classmethod
    def _check_path(cls, value: str) -> str:
        return normalize_source_path(value)

    @field_validator("rule_id")
    @classmethod
    def _check_rule_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("rule_id 不能为空")
        return normalized


class CorpusManifest(StrictModel):
    """摄取清单（knowledge/corpus.yaml）的内存形态；数据集名必须唯一。"""

    version: int = Field(ge=1)
    policy: CorpusPolicy = Field(default_factory=CorpusPolicy)
    datasets: Tuple[CorpusDataset, ...] = ()
    restricted_datasets: Tuple[str, ...] = ()
    quarantine: Tuple[CorpusQuarantine, ...] = ()
    rule_sources: Tuple[CorpusRuleSource, ...] = ()

    @field_validator("restricted_datasets")
    @classmethod
    def _check_restricted(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(sorted({normalize_dataset_name(item) for item in values}))

    @model_validator(mode="after")
    def _unique_datasets(self) -> "CorpusManifest":
        seen: dict[str, str] = {}
        for dataset in self.datasets:
            if dataset.name in seen:
                raise ValueError(f"数据集名重复：{dataset.name}")
            seen[dataset.name] = dataset.name
        declared = {dataset.name for dataset in self.datasets}
        unknown = sorted(set(self.restricted_datasets) - declared)
        if unknown:
            raise ValueError(f"restricted_datasets 引用了未声明的数据集：{unknown}")
        for item in self.rule_sources:
            if item.dataset not in declared:
                raise ValueError(f"rule_sources 引用了未声明的数据集：{item.dataset}")
        return self

    def dataset(self, name: str) -> CorpusDataset:
        normalized = normalize_dataset_name(name)
        for item in self.datasets:
            if item.name == normalized:
                return item
        known = sorted(item.name for item in self.datasets)
        raise CorpusError(f"未知数据集 {name!r}；清单里只有 {known}")

    @property
    def dataset_names(self) -> Tuple[str, ...]:
        return tuple(sorted(item.name for item in self.datasets))


class ResolvedEntry(StrictModel):
    """已解析的入口：把镜像 manifest 的元数据（URL/标题/哈希/许可）固定下来。"""

    dataset: str
    source_path: str
    title: str
    source_url: str
    license: str
    license_source: Optional[str] = None
    tier: Tier
    visibility: Visibility
    language: Optional[str] = None
    manifest_sha256: Optional[str] = None
    manifest_bytes: Optional[int] = None
    mirror_revision: Optional[str] = None

    @field_validator("manifest_sha256")
    @classmethod
    def _check_manifest_hash(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized.startswith("sha256:"):
            normalized = normalized[len("sha256:") :]
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError(f"manifest_sha256 必须是 64 位十六进制摘要，得到 {value!r}")
        return "sha256:" + normalized

    @property
    def document_id(self) -> str:
        return document_id_for(self.dataset, self.source_path)


class ChunkDraft(StrictModel):
    """分块器的输出：一段**原文**（不解释、不改写）及其结构信息。"""

    chunk_id: str
    document_id: str
    ordinal: int = Field(ge=0)
    heading_path: Tuple[str, ...] = ()
    heading_anchor: str = Field(min_length=1)
    text: str
    text_hash: str
    char_count: int = Field(ge=0)
    kind: ChunkKind = ChunkKind.PROSE
    part_index: int = Field(default=1, ge=1)
    truncated: bool = False
    original_chars: Optional[int] = None
    oversized: bool = False

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> "ChunkDraft":
        if self.char_count != len(self.text):
            raise ValueError("char_count 必须等于 text 的字符数")
        if self.text_hash != sha256_text(self.text):
            raise ValueError("text_hash 必须等于 text 的哈希")
        if self.truncated and self.original_chars is None:
            raise ValueError("标记为截断时必须记录 original_chars")
        return self

    @property
    def heading_display(self) -> str:
        return " > ".join(self.heading_path)


class ChunkRecord(ChunkDraft):
    """库里的 chunk：draft 加上 revision 与隔离标记。"""

    revision: int = Field(default=1, ge=1)
    quarantined: bool = False


class ChunkChange(StrictModel):
    """一次文档重建的差异：只动真正变化的 chunk。"""

    created: Tuple[str, ...] = ()
    updated: Tuple[str, ...] = ()
    unchanged: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()

    @property
    def changed(self) -> Tuple[str, ...]:
        return tuple(sorted(set(self.created) | set(self.updated)))


class DocumentRecord(StrictModel):
    """库里的文档行。content_hash 是本地内容哈希，manifest_hash 是镜像清单记录的哈希。"""

    document_id: str
    dataset: str
    source_path: str
    source_url: str
    title: str
    license: str
    license_source: Optional[str] = None
    tier: Tier
    visibility: Visibility
    language: Optional[str] = None
    content_hash: str
    manifest_hash: Optional[str] = None
    byte_size: int = Field(ge=0)
    mirror_revision: Optional[str] = None
    chunker_version: str = CHUNKER_VERSION
    ingested_at: str = ""

    @property
    def hash_drift(self) -> bool:
        """镜像清单哈希与本地内容哈希不一致：说明本地文件在上游记录之外被改过。"""

        return self.manifest_hash is not None and self.manifest_hash != self.content_hash


class IndexRunRecord(StrictModel):
    """一次索引 run 的台账。status=running 只表示进程还活着。"""

    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    input_hash: str
    status: IndexRunStatus
    documents_indexed: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0
    chunks_unchanged: int = 0
    chunks_removed: int = 0
    documents_removed: int = 0
    truncated_chunks: int = 0
    oversized_chunks: int = 0
    empty_sections: int = 0
    quarantined_chunks: int = 0
    note: Optional[str] = None


class QuarantinedChunk(StrictModel):
    """被隔离的 chunk 记录：保留原因与当时的文本哈希，供审计与自动失效。"""

    chunk_id: str
    document_id: str
    text_hash: str
    reason: str
    quarantined_at: str


class AccessScope(StrictModel):
    """调用方的检索授权范围：主体 + 允许的数据集集合。

    授权只来自显式声明；查询文本、文件路径、数据集名都不能扩权。
    """

    subject: str = Field(min_length=1)
    datasets: FrozenSet[str] = Field(default_factory=frozenset)
    allow_restricted: bool = Field(
        default=False,
        description="是否允许检索 visibility=restricted 的数据集；默认关闭，必须显式打开",
    )

    @field_validator("subject")
    @classmethod
    def _check_subject(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AccessScope.subject 不能为空")
        return normalized

    @field_validator("datasets", mode="before")
    @classmethod
    def _check_datasets(cls, value: Any) -> Any:
        if value is None:
            return frozenset()
        if isinstance(value, str):
            raise TypeError("datasets 必须是数据集名的序列，不能是字符串")
        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(normalize_dataset_name(str(item)) for item in value if str(item).strip())
        return value

    @property
    def identity(self) -> str:
        """用于缓存键：主体 + 排序后的数据集权限。权限变化必然换键。"""

        marker = "restricted-allowed" if self.allow_restricted else "public-only"
        return self.subject + "|" + marker + "|" + ",".join(sorted(self.datasets))


class RetrievalQuery(StrictModel):
    """一次检索请求：自由文本 + 受控的结构化字段。

    text 永远是**数据**：它只参与词法匹配，不参与过滤条件的构造，也不会被写进 SQL。
    """

    text: Optional[str] = None
    file: Optional[str] = None
    language: Optional[str] = None
    module: Optional[str] = None
    operation: Optional[Operation] = None
    datasets: Tuple[str, ...] = ()
    tiers: Tuple[Tier, ...] = ()
    languages: Tuple[str, ...] = ()
    limit: Optional[int] = Field(default=None, ge=1, le=50)
    request_id: Optional[str] = None
    trace_id: Optional[str] = None

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_repo_path(value)

    @field_validator("language", "module")
    @classmethod
    def _check_dimension(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("结构化字段不能是空字符串；不知道就写 null")
        return normalized

    @field_validator("datasets")
    @classmethod
    def _check_datasets(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(sorted({normalize_dataset_name(item) for item in values}))

    @field_validator("languages")
    @classmethod
    def _check_languages(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(sorted({canonical_identifier(item) for item in values}))

    @classmethod
    def from_context(
        cls,
        context: PolicyContext,
        *,
        text: Optional[str] = None,
        datasets: Tuple[str, ...] = (),
        tiers: Tuple[Tier, ...] = (),
        limit: Optional[int] = None,
    ) -> "RetrievalQuery":
        """从 PolicyContext 构造查询：只搬运显式字段，绝不推断。"""

        if not isinstance(context, PolicyContext):
            raise QueryError(f"from_context 只接受 PolicyContext，得到 {type(context).__name__}")
        return cls(
            text=text if text is not None else context.task,
            file=context.file,
            language=context.language,
            module=context.module,
            operation=context.operation,
            datasets=datasets,
            tiers=tiers,
            limit=limit,
            request_id=context.request_id,
            trace_id=context.trace_id,
        )


class QueryFilters(StrictModel):
    """检索的硬过滤条件：只能由受控字段构造，且只以参数形式进入 SQL。"""

    datasets: Tuple[str, ...] = ()
    tiers: Tuple[str, ...] = ()
    languages: Tuple[str, ...] = ()
    scope_datasets: Tuple[str, ...] = Field(
        default=(), description="调用方 AccessScope 允许的数据集；空集合表示不允许检索任何数据集"
    )


class QueryPlan(StrictModel):
    """查询计划：规范化文本 → 词项（含扩展）→ 过滤条件 → 可重放的 FTS 表达式。

    表达式只由双引号包裹的词项与 OR 组成：用户文本里出现的引号、括号、NEAR/*/^ 等
    FTS 操作符在规范化阶段就被剔除，无法改变查询结构。
    """

    text: str
    terms: Tuple[str, ...] = ()
    expanded_terms: Tuple[str, ...] = ()
    structural_terms: Tuple[str, ...] = ()
    filters: QueryFilters = Field(default_factory=QueryFilters)
    fts_expression: str = ""
    limit: int = Field(default=5, ge=1, le=50)
    truncated: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.terms


class RetrievedChunk(StrictModel):
    """一条检索命中：来源、位置、排名、方式与原文都在这里，score 只用于内部排序。"""

    chunk_id: str
    document_id: str
    dataset: str
    source_path: str
    source_url: str
    license: str
    tier: Tier
    visibility: Visibility
    title: str
    heading_path: Tuple[str, ...] = ()
    heading_anchor: str = ""
    ordinal: int = Field(default=0, ge=0)
    rank: int = Field(ge=1)
    score: float = 0.0
    method: RetrievalMethod = RetrievalMethod.FTS5
    text: str = ""
    text_hash: str = ""
    char_count: int = Field(default=0, ge=0)
    truncated: bool = False
    oversized: bool = False

    @property
    def citation_source(self) -> str:
        return f"{self.source_path}#{self.heading_anchor}" if self.heading_anchor else self.source_path


class RetrievalResult(StrictModel):
    """一次检索的完整结果：状态、查询、索引版本与命中列表（顺序即排名）。"""

    status: RetrievalStatus
    query: str = ""
    plan: Optional[QueryPlan] = None
    method: RetrievalMethod = RetrievalMethod.FTS5
    index_version: str = ""
    results: Tuple[RetrievedChunk, ...] = ()
    reason: Optional[UnavailableReason] = None
    detail: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None

    @model_validator(mode="after")
    def _status_matches_results(self) -> "RetrievalResult":
        if self.status is RetrievalStatus.OK and not self.results:
            raise ValueError("status=ok 必须带至少一条命中")
        if self.status is not RetrievalStatus.OK and self.results:
            raise ValueError("status 不是 ok 时不得携带命中结果")
        if self.status is RetrievalStatus.EMPTY and self.reason is None:
            raise ValueError("status=empty 必须说明原因")
        if self.status is RetrievalStatus.UNAVAILABLE and self.reason is None:
            raise ValueError("status=unavailable 必须说明原因")
        return self

    @property
    def top(self) -> Optional[RetrievedChunk]:
        return self.results[0] if self.results else None


class PolicyFact(StrictModel):
    """来自 Policy Engine 的权威片段：不是检索结果，因此不接受检索分数或排名。"""

    rule_id: str = Field(min_length=1, description="审计身份，形如 ARCH-001@1")
    severity: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_path: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator("source_path")
    @classmethod
    def _check_source_path(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_repo_path(value)


class DroppedSnippet(StrictModel):
    """被 Context Builder 丢弃的片段：去重或预算，原因必须可解释。"""

    chunk_id: str
    reason: str
    duplicate_of: Optional[str] = None


class ContextSnippet(StrictModel):
    """Context 中的一段参考：带引用 ID、来源与哈希，边界明确。"""

    citation_id: str = Field(min_length=1)
    chunk_id: str
    document_id: str
    dataset: str
    source_path: str
    source_url: str
    license: str
    tier: Tier
    title: str
    heading_path: Tuple[str, ...] = ()
    heading_anchor: str = ""
    rank: int = Field(ge=1)
    score: float = 0.0
    method: RetrievalMethod = RetrievalMethod.FTS5
    text: str
    text_hash: str
    char_count: int = Field(ge=0)
    truncated: bool = False
    oversized: bool = False
    original_chars: Optional[int] = None

    @property
    def citation(self) -> str:
        return f"[{self.citation_id}] {self.source_path}#{self.heading_anchor}"


class EngineeringContext(StrictModel):
    """交给 Agent 的 Engineering Context：策略事实在前、参考资料在后，全部可追溯。"""

    status: ContextStatus
    reason: Optional[UnavailableReason] = None
    detail: Optional[str] = None
    query: str = ""
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    index_version: str = ""
    method: RetrievalMethod = RetrievalMethod.FTS5
    budget_chars: int = Field(ge=0)
    used_chars: int = Field(ge=0)
    policy_facts: Tuple[PolicyFact, ...] = ()
    snippets: Tuple[ContextSnippet, ...] = ()
    dropped: Tuple[DroppedSnippet, ...] = ()

    @property
    def citations(self) -> Tuple[str, ...]:
        return tuple(item.citation_id for item in self.snippets)

    @property
    def is_available(self) -> bool:
        return self.status is ContextStatus.OK

    @model_validator(mode="after")
    def _budget_is_respected(self) -> "EngineeringContext":
        if self.used_chars > self.budget_chars:
            raise ValueError(
                f"Context 超过预算：used={self.used_chars} budget={self.budget_chars}"
            )
        return self


class LayeredChunk(StrictModel):
    """排序用的内部结构：tier 优先级 + 排名，用于稳定重排。"""

    tier: Tier
    rank: int
    chunk: RetrievedChunk

    @property
    def sort_key(self) -> Tuple[int, int, str]:
        return (tier_priority(self.tier), self.rank, self.chunk.chunk_id)
