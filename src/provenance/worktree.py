"""控制面针脚：四个名字、一份实现（控制面重构方案 §3.1）。

四个名字回答四个不同的问题，各自都要能单独读数：

- `evidence_tree_digest`：取证时**那棵影子树**的指纹（AGENTS 第 48 条：证据的含义取决于
  取证时那棵树的形状）；
- `referenced_inputs_digest`：本次检查**声明的输入范围**（判据级封条）——用"声明"而不是
  "实际读过"：检查会拉起 pytest / ruff / mypy 子进程，纯标准库无法可靠观测它们读了什么，
  照"实际读过"写会造出第二件需要自证的仪器（评审批次 1 §2.3）；
- `workspace_tree_digest`：**整个工作树**（轮次级封条）——回答"这一轮有没有未声明的写者"；
- `platform_revision`：产出这条判定的**平台代码**（范围由声明给出，不写死目录）。

三条不可让步的性质：

1. **严格模式**：读不到的文件 / 目录 → `UnprovableError`，**不许静默少算**。
   `pre_evidence` 那份既有实现是**标注模式**（它的指纹只标注、不是封条），这里把两种口径写成
   同一个显式参数 `strict`，而不是两份实现——封条路径一律 strict；
2. **确定性**：条目按内容排序后再哈希，不依赖文件系统遍历顺序（AGENTS 第 19 条：相同输入
   必须得到逐字节相同的证据）；
3. **不一致只有一种解释**：`pre != post` → `external_write`；读不到 → `unprovable`。
   `pass` 只有在"三个指纹都相等"时才可能出现（方案 §5.3 的状态表）。

本模块**只依赖标准库**，也不 import adapters：它要能在任何一侧被调用——针脚实现自己坐在内核
目录会造成自干扰（评审批次 1 §2.4，所以它落在 `src/provenance/` 而不是 `src/policy/`）。
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

__all__ = [
    "DEFAULT_EXCLUDES",
    "LANDING_STATES",
    "SEAL_STATES",
    "Digest",
    "LandingStateError",
    "ProvenanceError",
    "SealComparison",
    "SealPoint",
    "UnprovableError",
    "compare_seals",
    "evidence_tree_digest",
    "load_declaration",
    "platform_revision",
    "referenced_inputs_digest",
    "resolve_landing_state",
    "seal",
    "tree_digest",
    "workspace_tree_digest",
]

# 轮次级封条默认排除的东西：构建产物、缓存、虚拟环境与忽略目录。**排除项是声明的**，
# 不是"看不见的默认值"：调用方可以整体替换它，替换后的取值会进回执。
DEFAULT_EXCLUDES: Tuple[str, ...] = (
    ".git/**",
    ".tmp/**",
    ".venv/**",
    "node_modules/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "**/*.egg-info/**",
)

# 三种落地状态不许折叠（方案 §9）：落在树上、被别人验过、被本轮独立复核过是三件事。
LANDING_STATES: Tuple[str, ...] = ("landed_unverified", "landed_peer_verified", "round_verified")

# 封条状态（方案 §5.3）。unprovable 由 UnprovableError 表达，不在这里出现——
# "读不到"不是一种比对结果，它是比对做不成。
SEAL_STATES: Tuple[str, ...] = ("pass", "external_write")


class ProvenanceError(Exception):
    """针脚的通用错误。"""


class UnprovableError(ProvenanceError):
    """证明不了：读不到声明的输入、声明一个文件都没命中、树根不存在。

    失败关闭：调用方必须把它当"本轮判据不成立"（方案 §5.3 的退出码 3），
    **不许**降级成"算不出来就当通过"。
    """


class LandingStateError(ProvenanceError):
    """落地状态非法或证明不了。"""


# --------------------------------------------------------------------------- 摘要


@dataclass(frozen=True)
class Digest:
    """一次指纹：名字、值、覆盖了多少文件与字节。"""

    name: str
    sha256: str
    files: int
    bytes: int

    def as_json(self) -> Dict[str, Any]:
        return {"name": self.name, "sha256": self.sha256, "files": self.files, "bytes": self.bytes}


# glob→正则的构造是纯函数、返回值不可变：按 pattern 缓存。`re` 只缓存 compile 之后的
# pattern，**不缓存这一步的逐字符字符串构造**，而它是遍历与命中判据的主路径（每个目录、
# 每个文件、每条声明都要走一遍，同一批 pattern 反复重建）。
@functools.lru_cache(maxsize=None)
def _compile(pattern: str) -> "re.Pattern[str]":
    """glob → 正则：`**/` 匹配零个或多个目录，`**` 跨目录，`*` 只在单段内，`?` 单字符。"""

    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**/", index):
                out.append("(?:.*/)?")
                index += 3
                continue
            if pattern.startswith("**", index):
                out.append(".*")
                index += 2
                continue
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


def _matches(pattern: str, relative: str) -> bool:
    return _compile(pattern).match(relative) is not None


def _excluded(relative: str, excludes: Sequence[str]) -> bool:
    """相对路径是否命中排除 glob。

    目录要按"名字"与"名字 + /"两种写法各试一次：`**/__pycache__/**` 命中 `__pycache__/`
    而不命中 `__pycache__`；只试一种写法会让"排除 __pycache__"变成"排除它下面的文件、
    但照样走进去"。
    """

    for pattern in excludes:
        if _matches(pattern, relative) or _matches(pattern, relative + "/"):
            return True
    return False


def _relative(path: Path, root: Path) -> str:
    """仓库相对路径（POSIX 分隔符）；等于根目录时返回 "."。

    这里**不做 resolve()**：解析会跟随符号链接——指向工作区之外的链接让 relative_to
    失败，然后退回一个随调用方式变化的（可能绝对的）路径，同一棵树换个挂载点就得到另一个
    指纹（确定性要求 2）；留在根内的链接也会被记成目标的相对路径，制造重复键。
    词法相对路径记录的是"链接本身"，正是遍历看到的那一项。
    """

    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:  # pragma: no cover - 不同盘符（Windows）没有相对形式
        return path.as_posix()


def _read_bytes(path: Path) -> bytes:
    """唯一的读入口：测试替换它就能造出"读不到"，不必真去改文件权限。"""

    return path.read_bytes()


def _walk(
    root: Path, *, strict: bool, excludes: Sequence[str] = ()
) -> Iterable[Tuple[str, Path]]:
    """走这棵树。`excludes` 命中的**目录不再走进去**——排除是声明，不是过滤。

    这一点是刻意的：如果排除只作用在"把文件丢出指纹"这一步，一个读不到的 `.tmp` 子目录
    照样会让整棵树变成 unprovable——而它本来就不在声明范围内。排除项会随回执一起写出来，
    所以"排除了什么"是可读的，不是看不见的默认值。
    """

    root = Path(root)
    if not root.is_dir():
        raise UnprovableError(f"树根不存在或不是目录：{root}（读不到就不算数）")

    def onerror(error: OSError) -> None:
        if strict:
            raise UnprovableError(f"读不到目录：{error.filename}（{error.strerror}）") from error

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        here = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            if excludes and _excluded(_relative(here / name, root), excludes):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            candidate = here / name
            if not candidate.is_file():
                continue
            yield _relative(candidate, root), candidate


def _fingerprint(
    items: Iterable[Tuple[str, Path]],
    *,
    name: str,
    excludes: Sequence[str],
    strict: bool,
) -> Tuple[Digest, Dict[str, str]]:
    lines: list[str] = []
    hashes: Dict[str, str] = {}
    total = 0
    for relative, path in items:
        if _excluded(relative, excludes):
            continue
        try:
            data = _read_bytes(path)
        except OSError as error:
            if strict:
                raise UnprovableError(
                    f"读不到 {relative}（{error.strerror or error}）：封条不许静默少算"
                ) from error
            continue  # 标注模式：这份指纹只标注，不是封条
        value = hashlib.sha256(data).hexdigest()
        hashes[relative] = value
        lines.append(f"{relative} {value}")
        total += len(data)
    digest = "sha256:" + hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    return Digest(name=name, sha256=digest, files=len(lines), bytes=total), hashes


def tree_digest(
    root: Path | str,
    *,
    excludes: Sequence[str] = (),
    strict: bool = True,
    name: str = "tree",
) -> Digest:
    """整棵树的指纹：仓库相对路径 + 文件 sha256，按稳定顺序覆盖。"""

    return _fingerprint(
        _walk(Path(root), strict=strict, excludes=excludes),
        name=name,
        excludes=excludes,
        strict=strict,
    )[0]


def evidence_tree_digest(root: Path | str, *, strict: bool = True) -> Digest:
    """取证时那棵影子树的指纹（四个针脚之一）。

    `strict=False` 是**标注模式**：Phase 5 的取证摘要把指纹当"标注"用，读不到的副本不该让
    整个判定变成 evidence_unavailable；封条路径一律用默认的严格模式。
    """

    return tree_digest(root, strict=strict, name="evidence_tree_digest")


def workspace_tree_digest(
    root: Path | str, *, excludes: Sequence[str] = DEFAULT_EXCLUDES
) -> Digest:
    """整个工作树的指纹（轮次级封条）：回答"这一轮有没有未声明的写者"。"""

    return tree_digest(root, excludes=excludes, strict=True, name="workspace_tree_digest")


def _declared_digest(
    name: str,
    root: Path | str,
    declaration: Sequence[str],
    *,
    excludes: Sequence[str],
) -> Tuple[Digest, Dict[str, str]]:
    entries = [entry for entry in declaration if entry.strip()]
    if not entries:
        raise UnprovableError(
            "声明是空的：给不出 " + name + "。判据里不许把「给不出」当成 pass（方案 §5.3）"
        )
    relative_root = Path(root)
    # 排除项要在**候选集**里就过滤掉：_walk 只剪掉被排除的目录，被排除的**文件**
    # （`**/*.pyc` 这类）照样会被列出来。声明若只命中这些文件，它们会在 _fingerprint
    # 里被静默丢掉，得到的是一份覆盖 0 个文件的指纹（空串的 sha256）——那正是本模块
    # 承诺要防的"静默少算"：这样的声明会变得可以被封条、也可以被复核。
    available = [
        (relative, path)
        for relative, path in _walk(relative_root, strict=True, excludes=excludes)
        if not _excluded(relative, excludes)
    ]
    resolved: Dict[str, Path] = {}
    unmatched: list[str] = []
    for pattern in entries:
        hits = [(relative, path) for relative, path in available if _matches(pattern, relative)]
        if not hits:
            unmatched.append(pattern)
            continue
        for relative, path in hits:
            resolved[relative] = path
    if unmatched:
        raise UnprovableError(
            "声明的输入一个文件都没命中：" + "、".join(unmatched) + "（声明不足或写错，都不算数）"
        )
    return _fingerprint(sorted(resolved.items()), name=name, excludes=excludes, strict=True)


def referenced_inputs_digest(
    root: Path | str,
    declaration: Sequence[str],
    *,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
) -> Digest:
    """本次检查**声明的输入范围**的指纹（判据级封条）。

    声明的每一条都必须命中至少一个文件：一条都不命中的声明不是"范围为空"，是"证明不了"
    ——否则"把声明写成空壳"就能让任何检查拿到 pass。
    """

    return _declared_digest(
        "referenced_inputs_digest", root, declaration, excludes=excludes
    )[0]


def platform_revision(
    root: Path | str,
    declaration: Sequence[str],
    *,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
) -> Digest:
    """产出这条判定的**平台代码**的指纹：范围由声明给出，不写死目录（方案 §10 第 4 条）。"""

    return _declared_digest("platform_revision", root, declaration, excludes=excludes)[0]


# --------------------------------------------------------------------------- 封条


@dataclass(frozen=True)
class SealPoint:
    """一次封条：三个指纹 + 工作树的逐文件哈希（用于算差集，不进回执）。"""

    referenced: Digest
    workspace: Digest
    platform: Digest
    file_hashes: Mapping[str, str]
    excludes: Tuple[str, ...] = ()

    def as_json(self) -> Dict[str, Any]:
        return {
            "referenced_inputs_digest": self.referenced.sha256,
            "workspace_tree_digest": self.workspace.sha256,
            "platform_revision": self.platform.sha256,
            "workspace_excludes": list(self.excludes),
        }


def seal(
    root: Path | str,
    declaration: Sequence[str],
    platform_inputs: Sequence[str],
    *,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
) -> SealPoint:
    """`seal(pre) → 跑判据 → seal(post)` 里的那一次采样（方案 §5.3）。"""

    referenced, _ = _declared_digest(
        "referenced_inputs_digest", root, declaration, excludes=excludes
    )
    workspace, hashes = _fingerprint(
        _walk(Path(root), strict=True, excludes=excludes),
        name="workspace_tree_digest",
        excludes=excludes,
        strict=True,
    )
    platform, _ = _declared_digest(
        "platform_revision", root, platform_inputs, excludes=excludes
    )
    return SealPoint(
        referenced=referenced,
        workspace=workspace,
        platform=platform,
        file_hashes=hashes,
        excludes=tuple(excludes),
    )


@dataclass(frozen=True)
class SealComparison:
    """两次封条的比对：状态只有两个（pass / external_write）；unprovable 由异常表达。"""

    state: str
    added: Tuple[str, ...]
    modified: Tuple[str, ...]
    removed: Tuple[str, ...]
    before: Mapping[str, str]
    after: Mapping[str, str]

    @property
    def differences(self) -> Dict[str, Any]:
        return {
            "added": list(self.added),
            "modified": list(self.modified),
            "removed": list(self.removed),
        }


def compare_seals(pre: SealPoint, post: SealPoint) -> SealComparison:
    """比对两次封条。`pass` 要求三个指纹**都**相等：工作树、声明的输入、平台代码。"""

    before, after = pre.file_hashes, post.file_hashes
    added = tuple(sorted(set(after) - set(before)))
    removed = tuple(sorted(set(before) - set(after)))
    modified = tuple(sorted(k for k in set(before) & set(after) if before[k] != after[k]))
    same = (
        pre.workspace.sha256 == post.workspace.sha256
        and pre.referenced.sha256 == post.referenced.sha256
        and pre.platform.sha256 == post.platform.sha256
    )
    return SealComparison(
        state="pass" if same else "external_write",
        added=added,
        modified=modified,
        removed=removed,
        before={"referenced": pre.referenced.sha256, "workspace": pre.workspace.sha256,
                "platform": pre.platform.sha256},
        after={"referenced": post.referenced.sha256, "workspace": post.workspace.sha256,
               "platform": post.platform.sha256},
    )


# --------------------------------------------------------------------------- 落地状态与声明


def resolve_landing_state(
    requested: str, *, peer_evidence: Optional[Mapping[str, Any]] = None
) -> str:
    """校验落地状态：三种状态不许折叠，也不许"够不着就往上写"（方案 §9）。

    - `landed_unverified`：落在树上，没有任何独立验收——一次封条运行最多只能到这里；
    - `landed_peer_verified`：要交出验收者与证据摘要（`verifier` / `artifact` / `sha256`）；
    - `round_verified`：**只能由轮次级验收签发**，本工具不签发（一次封条不等于一轮验收）。
    """

    if requested not in LANDING_STATES:
        raise LandingStateError(
            f"未知落地状态 {requested!r}：只接受 {' / '.join(LANDING_STATES)}（不猜、不兜底）"
        )
    if requested == "round_verified":
        raise LandingStateError(
            "round_verified 只能由轮次级验收签发：一次封条运行不构成轮次验收（三态不许折叠）"
        )
    if requested == "landed_peer_verified":
        if peer_evidence is None:
            raise LandingStateError("landed_peer_verified 必须交出 peer_evidence，缺了就是证明不了")
        # 只接受**真的给了字符串**：str(None) 会变成真值 "None"，于是
        # {"verifier": null, "artifact": null} 这样一份伪造的 peer 验收会被放进来；
        # 数字同样不行（一个 64 位十进制整数能骗过 sha256 的正则）。
        raw_verifier = peer_evidence.get("verifier")
        raw_artifact = peer_evidence.get("artifact")
        raw_digest = peer_evidence.get("sha256")
        verifier = raw_verifier.strip() if isinstance(raw_verifier, str) else ""
        artifact = raw_artifact.strip() if isinstance(raw_artifact, str) else ""
        digest = raw_digest.strip() if isinstance(raw_digest, str) else ""
        if not verifier or not artifact:
            raise LandingStateError("peer_evidence 缺 verifier 或 artifact（谁验的、验的是哪份）")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LandingStateError("peer_evidence.sha256 必须是 64 位小写十六进制")
    return requested


def load_declaration(path: Path | str) -> Tuple[str, ...]:
    """读声明文件：一行一条 glob，`#` 开头与空行忽略。"""

    target = Path(path)
    if not target.is_file():
        raise UnprovableError(f"声明文件不存在：{target}")
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        # is_file() 与 read 之间文件可能被删 / 改权限，也可能不是 UTF-8：这些都必须落
        # UnprovableError——调用方按文档只认它（"证明不了"，退出码 3），裸 OSError /
        # UnicodeDecodeError 会被当成别的东西，而这条路径正是"读不到声明"的那一条。
        raise UnprovableError(
            f"声明文件读不出来：{target}（{type(error).__name__}: {error}）"
        ) from error
    entries: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return tuple(entries)
