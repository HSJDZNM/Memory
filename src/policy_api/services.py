"""租户服务的装配：规则集、检索索引、验证器配置。

三条设计约束：

1. **原子装配**：一个租户要么完整可用，要么在 readiness 里显式失败。
   规则目录读不出来就是 `rule_set_unavailable`，不会退回"没有规则 = 全部放行"；
2. **懒加载 + 身份校验**：索引与验证器配置在第一次真正用到时加载，之后每次请求都校验
   身份签名（索引世代 / 规则文件指纹）。签名变了才重新加载——**配置热更新与 evaluate
   并发时，每个请求仍然只用一份完整规则集**（RuleSet 是不可变对象，替换是整体的）；
3. **一个请求一个连接**：SQLite 句柄不跨线程共享（`retrieval.store.ChunkStore` 的
   连接是 `check_same_thread=True`），因此每次检索都开一个新句柄并关掉；
   索引本身是**只读**的，服务不会在服务过程中重建它（重建是离线动作）。
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
import yaml

from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from policy.loader import LoaderError, load_rule_set
from policy.models import RuleSet

from .config import ApiConfig, ConfigError, TenantSpec
from .errors import ApiError, ErrorCode

__all__ = ["LoadedTenant", "TenantService", "TenantStore", "signature_of"]


def signature_of(paths: Tuple[Path, ...]) -> str:
    """文件集合的指纹：路径 + mtime + 大小。变了就重载，不变就复用。"""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(str(path).encode("utf-8"))
        try:
            stat = path.stat()
        except OSError:
            digest.update(b"<missing>")
            continue
        digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
    return digest.hexdigest()


@dataclass
class LoadedTenant:
    """一个已经装配好的租户：规则集 + 边界 + 懒加载的检索/验证器句柄。"""

    spec: TenantSpec
    root: Path
    project_root: Path
    rule_dirs: Tuple[Path, ...]
    store_path: Optional[Path]
    corpus_path: Optional[Path]
    expansion_path: Optional[Path]
    validation_root: Optional[Path]
    # 注册表文件本身也是**相对路径**，而 `validators.registry.load_config(registry=...)` 用的是
    # `Path(registry)`（相对**进程工作目录**，不是 root）。同一个租户的其余路径都按锚点解析，
    # 只有这一处不解析就会随 cwd 漂移：换个目录启动服务，readiness 就从 ready 变成
    # validator_unavailable。因此这里把它解析成绝对路径后再传下去（见 validators()）。
    validators_path: Optional[Path]
    audit_path: Optional[Path]
    _rules: Optional[RuleSet] = None
    _rules_signature: str = ""
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ------------------------------------------------------------------ 规则集

    def rules(self) -> RuleSet:
        """取当前规则集；规则文件变了就整份换掉（不会出现半套规则）。"""

        with self._lock:
            signature = signature_of(self._rule_files())
            if self._rules is not None and signature == self._rules_signature:
                return self._rules
            try:
                loaded = load_rule_set(list(self.rule_dirs), repo_root=self.root)
            except LoaderError as error:
                raise ApiError(
                    ErrorCode.RULE_SET_UNAVAILABLE,
                    f"租户 {self.spec.tenant_id} 的规则集不可加载（{type(error).__name__}）",
                    retryable=True,
                ) from error
            if not loaded.rules and self._rules is not None:
                # 规则目录被清空：拒绝用空规则集替换掉正在服务的规则集。
                raise ApiError(
                    ErrorCode.RULE_SET_UNAVAILABLE,
                    f"租户 {self.spec.tenant_id} 的规则集变成空集；拒绝以空规则集继续服务",
                    retryable=True,
                )
            self._rules = loaded
            self._rules_signature = signature
            return loaded

    def rule_set_hash(self) -> Optional[str]:
        try:
            return self.rules().identity
        except ApiError:
            return None

    def _rule_files(self) -> Tuple[Path, ...]:
        files: list[Path] = []
        for directory in self.rule_dirs:
            if directory.is_file():
                files.append(directory)
            elif directory.is_dir():
                files.extend(sorted(directory.rglob("*.yaml")))
                files.extend(sorted(directory.rglob("*.yml")))
        return tuple(files)

    # ------------------------------------------------------------------ 检索

    def corpus_root(self) -> Path:
        """语料清单的锚点：清单里 `mirror` 是相对**清单根**的路径。

        与`retrieval.cli` 一样，先看 `<清单目录>/<mirror>` 是否存在；
        清单根通常就是仓库根（`knowledge/corpus.yaml`），但独立部署时清单可以自带镜像目录，
        此时锚点必须是清单目录本身——用错锚点会把"镜像不存在"误报成"知识不可用"。
        """

        assert self.corpus_path is not None
        anchor = self.corpus_path.parent
        try:
            document = yaml.safe_load(self.corpus_path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - 读不出来就退回清单目录，由 load_corpus 报真错
            return anchor
        mirrors = [
            str(item.get("mirror"))
            for item in (document.get("datasets") or [])
            if isinstance(item, Mapping) and item.get("mirror")
        ]
        if not mirrors:
            return anchor
        for candidate in (anchor, *anchor.parents, self.root, *self.root.parents):
            if all((candidate / mirror).is_dir() for mirror in mirrors):
                return candidate
        return anchor

    def corpus(self) -> Any:
        """加载语料清单（每次调用都重新读，检索是低频且清单很小）。"""

        if self.corpus_path is None:
            raise ApiError(
                ErrorCode.KNOWLEDGE_UNAVAILABLE,
                f"租户 {self.spec.tenant_id} 没有配置检索语料清单；检索不可用时不得回退到模型记忆",
            )
        from retrieval.corpus import load_corpus

        try:
            return load_corpus(self.corpus_path, repo_root=self.corpus_root())
        except Exception as error:  # noqa: BLE001 - 配置错误一律失败关闭
            raise ApiError(
                ErrorCode.KNOWLEDGE_UNAVAILABLE,
                f"租户 {self.spec.tenant_id} 的语料清单不可加载（{type(error).__name__}）",
                retryable=True,
            ) from error

    def lexicon(self) -> Optional[Any]:
        if self.expansion_path is None:
            return None
        from retrieval.corpus import load_expansion

        try:
            return load_expansion(self.expansion_path, repo_root=self.root)
        except Exception as error:  # noqa: BLE001
            raise ApiError(
                ErrorCode.KNOWLEDGE_UNAVAILABLE,
                f"租户 {self.spec.tenant_id} 的术语表不可加载（{type(error).__name__}）",
                retryable=True,
            ) from error

    def validators(self) -> Any:
        if self.validation_root is None:
            raise ApiError(
                ErrorCode.VALIDATOR_UNAVAILABLE,
                f"租户 {self.spec.tenant_id} 没有配置验证器注册表；证据类 checker 无法产出证据",
            )
        from validators.registry import load_config

        try:
            return load_config(
                root=self.validation_root,
                registry=self.validators_path,
            )
        except Exception as error:  # noqa: BLE001 - 注册表/档案不合法就是不可用
            raise ApiError(
                ErrorCode.VALIDATOR_UNAVAILABLE,
                f"租户 {self.spec.tenant_id} 的验证器配置不可加载（{type(error).__name__}）",
                retryable=True,
            ) from error


class TenantStore:
    """全部租户的装配结果。装配不完整时 readiness 必须失败。"""

    def __init__(self, config: ApiConfig, *, root: Path) -> None:
        self.config = config
        self.root = Path(root).resolve()
        self.config_dir = (
            None if not config.config_dir else Path(config.config_dir).resolve()
        )
        self._lock = threading.RLock()
        self._tenants: dict[str, LoadedTenant] = {}
        self._errors: dict[str, str] = {}

    def load(self) -> "TenantStore":
        """装配每个启用的租户；单个租户失败只记错误，不拖垮其他租户。

        readiness 会把这些错误显式报出来——"某个租户装不上"是必须被看见的事实，
        不是启动日志里的一行警告。
        """

        with self._lock:
            for spec in self.config.tenants:
                if not spec.enabled:
                    continue
                try:
                    self._tenants[spec.tenant_id] = self._assemble(spec)
                except ConfigError as error:
                    self._errors[spec.tenant_id] = str(error)
                except OSError as error:
                    self._errors[spec.tenant_id] = f"{type(error).__name__}: {error}"
            return self

    def _resolve(self, value: Optional[str], *, base: Optional[Path] = None) -> Optional[Path]:
        if value is None:
            return None
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        anchor = base if base is not None else self.root
        primary = (anchor / candidate).resolve()
        if primary.exists():
            return primary
        # 第二锚点：配置文件所在目录。它让"部署配置与它引用的目录放在一起"成为可能
        # （临时环境、独立部署包），同时不动第一锚点的语义：**仓库根优先**。
        if self.config_dir is not None:
            fallback = (self.config_dir / candidate).resolve()
            if fallback.exists():
                return fallback
        return primary

    def _assemble(self, spec: TenantSpec) -> LoadedTenant:
        root = self._resolve(spec.rules_root) or self.root
        project_root = self._resolve(spec.project_root)
        if project_root is None:
            raise ConfigError(f"tenant {spec.tenant_id!r} 没有声明 project_root")
        if not project_root.is_dir():
            raise ConfigError(
                f"tenant {spec.tenant_id!r} 的 project_root 不存在: {project_root.name}"
            )
        rule_dirs = tuple(self._resolve(item, base=root) for item in spec.rules)
        if not rule_dirs:
            raise ConfigError(f"tenant {spec.tenant_id!r} 没有声明任何规则目录")
        for directory in rule_dirs:
            if not directory.exists():
                raise ConfigError(
                    f"tenant {spec.tenant_id!r} 的规则目录不存在: {directory.name}"
                )
        retrieval = spec.retrieval
        store_path = None
        corpus_path = None
        expansion_path = None
        if retrieval is not None and retrieval.enabled:
            store_path = self._resolve(retrieval.database)
            corpus_path = self._resolve(retrieval.corpus)
            expansion_path = self._resolve(retrieval.expansion)
        validation_root = self._resolve(spec.validation_root)
        # spec.validators 默认落在 validation_root 下（`validation/validators.yaml`）；
        # 它必须是绝对路径，理由见 LoadedTenant.validators_path 的注释。
        validators_path = self._resolve(spec.validators, base=validation_root or self.root)
        audit_path = self._resolve(spec.audit_log)
        return LoadedTenant(
            spec=spec,
            root=root,
            project_root=project_root,
            rule_dirs=rule_dirs,  # type: ignore[arg-type]
            store_path=store_path,
            corpus_path=corpus_path,
            expansion_path=expansion_path,
            validation_root=validation_root,
            validators_path=validators_path,
            audit_path=audit_path,
        )

    def get(self, tenant_id: str) -> LoadedTenant:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            detail = self._errors.get(tenant_id, "该租户没有被装配")
            raise ApiError(ErrorCode.TENANT_NOT_FOUND, detail, retryable=True)
        return tenant

    def has(self, tenant_id: str) -> bool:
        return tenant_id in self._tenants

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._tenants))

    @property
    def errors(self) -> Mapping[str, str]:
        return dict(self._errors)
