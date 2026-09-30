"""动手前取证（G3 / M2）：在影子工作区上跑 Phase 5 流水线，把证据交给引擎。

为什么需要它：`policy.engine.evaluate` 在 evidence=None 时把证据类 checker 的规则记进
`skipped_rules`；"跳过"不是"通过"，于是实测里 43 条规则只有 1 条真正参与判定
（M2：effective_rule_count ∈ {0, 1}）。本模块就是那条缺失的接线——把"这次写类动作改完
之后文件长什么样"落到一份**影子副本**上，跑真实验证器，把 `EvidenceBundle` 交给引擎，
证据类 checker 因此能在动手前判定。

三条不可让步的边界（对应 AGENTS.md 第 19 / 20 / 42 条）：

1. **证明不了就拒绝**：提议内容取不到、`edit` 的 old_string 在目标文件里不是恰好出现
   一次、平台数据读不到、超预算——一律 PreEvidenceError，由 Hook 转成
   exit 2 / `evidence_unavailable`。绝不回落到"没证据就当跳过"；
2. **影子工作区用完必删**：副本落在 `shadow_root/<动作标识>`（finally 删除），只复制
   未被 exclude glob 命中的内容；验证器绝不写进被治理项目；
3. **摘要里不出现绝对路径、不出现耗时**：进审计的是摘要（validator id + status、
   served_checkers、judgements、blockers、target 哈希），相同输入必须得到逐字节相同的摘要
   （AGENTS 第 19 条对证据的要求同样适用于它）；
4. **摘要必须说得出"这是哪棵树"**（P3）：证据的含义取决于取证时那棵树的形状——同一份文件、
   同一份配置，只改"兄弟模块在不在"，isort 的结论就会变（实测：先写测试时兄弟模块还不存在，
   那个模块被当成第三方 → I001 → warning）。因此摘要有 tree 段：范围、目标是否预先存在、
   树指纹（仓库相对路径 + 文件 sha256）、以及可选的项目内模块缺口。它只标注，不改判定。

验证器相关模块只在**函数内导入**：Hook 是长在工具执行前的进程入口，一个 import 期错误会让
它以内码 1 退出，而 dsh 把"非 0 非 2"当**非阻断失败**——工具照样执行。把这份风险压在
"声明了 pre_evidence 才会走到"的分支里，是这里唯一可接受的形状。
"""

from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.evidence import EvidenceBundle
from policy.models import PolicyContext, RuleSet
from provenance.worktree import evidence_tree_digest

from .adapter import TOOL_TABLE, AdapterConfig, PolicyEvent, ToolKind, glob_match

__all__ = ["PreEvidenceError", "PreEvidenceResult", "build_pre_evidence"]


class PreEvidenceError(Exception):
    """动手前取证失败：提议内容证明不了、平台数据不可用、超预算、流水线报错。

    调用方（Hook）必须把它转成失败关闭，不得降级成"没有证据就跳过"。
    """


@dataclass(frozen=True)
class PreEvidenceResult:
    """一次取证的产物：给引擎的证据包 + 给审计的脱敏摘要。"""

    bundle: EvidenceBundle
    summary: Mapping[str, Any]


@dataclass(frozen=True)
class _Proposal:
    """「这次动作之后目标文件应该长什么样」，以及它是怎么算出来的。"""

    content: str
    source_field: str
    mode: str  # verbatim（整份文本）/ replacement（字面量替换）


# 摘要里单个字符串的上限：审计记录是给人读的一等输出，不是日志倾倒场。
_SUMMARY_TEXT_LIMIT = 600

# 与 hooks.sanitize 同一口径的最小脱敏。**不能** import hooks：hooks 要 import 本模块，
# 反向导入会成环。两份实现都不许扩散：这里只处理"摘要里可能出现的绝对路径与凭据样式"。
# 绝对路径的识别必须带**边界**：没有边界的 "/" 会把普通仓库相对路径
# （src/shop/order_service.py）也当成绝对路径，账本里于是只剩 "src<abs>"，
# 而"这次查的是哪个文件"正是审计要回答的问题。边界 = 串首，或空白 / 引号 /
# 括号 / 等号 / 冒号 / 逗号之后。
_ABS_PATH_BOUNDARY = r"(?:(?<=[\s'\"(\[=:,])|^)"
_ABS_PATH_RE = re.compile(_ABS_PATH_BOUNDARY + r"(?:[A-Za-z]:[\\/]|\\\\|/)[^\s'\"]+")
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|api[_-]?key\s*[=:]\s*\S+|authorization:\s*\S+|bearer\s+\S+)"
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# P3：影子树的形状。取证摘要必须能回答"这条证据属于哪棵树"，因为同一份文件、同一份配置，
# 只改"兄弟模块在不在"，工具结论就会变（07 号报告 §4 P3 的确定性复现）。
TREE_SCOPE = "current_disk_tree_plus_proposal"
TREE_NOTE = (
    "本次证据属于『当前磁盘树 + 本次提议内容』；同一批次里其它尚未落地的写入**不在**树里"
    "（Hook 每次只见一个文件）。实测后果：先写测试时，它要 import 的兄弟模块还不存在，"
    "isort 会把项目内模块判成第三方（I001），而交付态是干净的——同一份文件、同一份配置，"
    "只改「兄弟模块在不在」，工具结论就会变。tree_digest 是这棵树的指纹"
    "（仓库相对路径 + 文件 sha256，按稳定顺序算），两次证据的指纹不同就说明取证时树不同"
)
# Q7：待实现（pending_implementation）的读数口径。写死在摘要里，读账本的人不必去猜
# "allow 是不是等于测试通过了"。
PENDING_IMPLEMENTATION_NOTE = (
    "pending_implementation 里的 checker **不在** served_checkers 里：工具跑成了，但选中的测试"
    "因项目内还不存在的模块/名字而无法收集（待实现）。本次写入因此是 allow_with_warnings 放行的"
    "——「覆盖它的测试尚未能运行」这件事必须能从账本读到，不能被读成「查过了、没问题」；"
    "测试最终是否通过由后续动作的取证与 PostToolUse 事后核对负责"
)
TREE_GAPS_NOTE = (
    "只在「顶层包已经存在于影子树里、但这个模块的文件/包目录找不到」时报出——"
    "这正是 isort 会把项目内模块判成第三方的形状；口径是可能漏、不误报（顶层包不在树里的"
    "import 不报，它可能是第三方）。它只标注这棵树缺什么，不改判定"
)


def _redact_text(value: str) -> str:
    text = _CONTROL_RE.sub(" ", value)
    text = _ABS_PATH_RE.sub("<abs>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    if len(text) > _SUMMARY_TEXT_LIMIT:
        text = text[: _SUMMARY_TEXT_LIMIT - 3] + "..."
    return text


def _redact(value: Any) -> Any:
    """递归脱敏：摘要里任何一层字符串都不许带绝对路径、凭据或控制字符。"""

    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def build_pre_evidence(
    raw_payload: Any,
    *,
    event: PolicyEvent,
    config: AdapterConfig,
    rules: RuleSet,
    context: PolicyContext,
) -> PreEvidenceResult:
    """在影子工作区上取证，返回证据包与脱敏摘要。

    预算是**硬上限**：`pre_evidence.timeout_ms` 之内拿不到证据就抛 PreEvidenceError。
    复制工作区、重建提议内容、跑验证器全都算在这次预算里——把它们拆成几段各自计时，
    就等于把"总时长"重新变成猜的（而 Hook 被 dsh 杀掉在协议里等于放行）。
    """

    pre = config.pre_evidence
    if pre is None:
        raise PreEvidenceError(
            "adapter 配置没有声明 pre_evidence：本次调用没有取证能力（这属于接线错误）"
        )
    if not pre.enabled:
        raise PreEvidenceError(
            "pre_evidence.enabled=false：声明了取证段但被显式关闭，不能按取证成功处理"
        )

    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["result"] = _collect_evidence(
                raw_payload, event=event, config=config, rules=rules, context=context
            )
        except BaseException as error:  # noqa: BLE001 - 任何异常都必须回到调用方
            box["error"] = error

    worker = threading.Thread(target=work, name="pre-evidence", daemon=True)
    worker.start()
    worker.join(pre.timeout_ms / 1000)
    if worker.is_alive():
        raise PreEvidenceError(
            f"动手前取证超过预算 {pre.timeout_ms} ms：验证器流水线没有在预算内交出证据，"
            "拒绝在证明不了的情况下放行"
        )

    error = box.get("error")
    if error is not None:
        if isinstance(error, PreEvidenceError):
            raise error
        # 未知异常同样按"取不到证据"处理：失败关闭的理由要能读，但不能把内部形状外泄。
        raise PreEvidenceError(
            f"动手前取证失败：{type(error).__name__}: {error}"
        ) from error
    return box["result"]


def _collect_evidence(
    raw_payload: Any,
    *,
    event: PolicyEvent,
    config: AdapterConfig,
    rules: RuleSet,
    context: PolicyContext,
) -> PreEvidenceResult:
    """取证的全部动作（在 build_pre_evidence 的预算线程里跑）。"""

    pre = config.pre_evidence
    assert pre is not None  # build_pre_evidence 已经检查过

    workspace = Path(pre.workspace)
    if not workspace.is_dir():
        raise PreEvidenceError("pre_evidence.workspace 不是目录：无法建立影子工作区")

    # 先算提议内容：证明不了就直接拒绝，连副本都不用建（少一次磁盘写、少一处残留）。
    proposal = _propose(raw_payload, event=event, workspace=workspace)
    anchor, resolution = _registry_anchor(Path(pre.registry_root))

    shadow_root = Path(pre.shadow_root)
    shadow = shadow_root / _shadow_name(event)
    _assert_shadow_is_disposable(workspace=workspace, shadow=shadow)
    if shadow.exists():
        # 上一次可能被强杀在半路（dsh 杀 Hook 是常见事件），残留必须当成不可信内容清掉。
        shutil.rmtree(shadow, ignore_errors=True)
    try:
        files_copied = _copy_workspace(
            workspace, shadow, exclude=pre.exclude, shadow_root=shadow_root
        )
        # 目标在提议之前是否已经存在：按**当前磁盘树**判定（write 新建 vs edit 改已有）。
        # 不能看影子副本：exclude 可能恰好不复制这个目标，那时"副本里没有"会被读成
        # "这次是新建"，而事实是"本次不复制它"——两件事不能混。
        target_existed_before = (workspace / event.file).is_file()
        _write_proposal(shadow, event.file, proposal.content)
        # 树指纹与缺口必须在**验证器跑之前**取：验证器可能在副本里留下 __pycache__ 之类的
        # 副产物，那之后再取指纹，"同一份输入"就会得到两个值。
        tree = _describe_tree(
            shadow=shadow,
            target_existed_before=target_existed_before,
            proposal=proposal,
            anchor=anchor,
        )
        report = _run_validators(
            pre=pre, anchor=anchor, event=event, context=context, rules=rules, shadow=shadow
        )
    finally:
        # 用完必删：副本是被治理项目的一份拷贝，留下来就是一份没人管的代码。
        shutil.rmtree(shadow, ignore_errors=True)

    bundle = report.bundle
    summary = _summary(
        report,
        bundle=bundle,
        pre=pre,
        resolution=resolution,
        proposal=proposal,
        files_copied=files_copied,
        repo_path=event.file,
        tree=tree,
    )
    return PreEvidenceResult(bundle=bundle, summary=summary)


# --------------------------------------------------------------------------- 提议内容


def _propose(raw_payload: Any, *, event: PolicyEvent, workspace: Path) -> _Proposal:
    """从 `tool_input` 重建"这次动作之后目标文件的内容"。

    字段名一律取自 TOOL_TABLE（数据），不在这里另写一张表：
    工具表与 manifest 的一致性由契约测试逐项比对，副本会漂移。

    为什么 `edit` 要求恰好一次命中：`replace_all` 为真且命中多处时，"替换范围到底覆盖
    哪几处"就变成了要靠猜的事；猜出来的内容会变成证据，而证据会变成放行理由。
    """

    tool_input = raw_payload.get("tool_input") if isinstance(raw_payload, Mapping) else None
    if not isinstance(tool_input, Mapping):
        raise PreEvidenceError("载荷缺少 tool_input（映射）：没有提议内容就无法取证")

    spec = TOOL_TABLE.get(event.tool)
    if spec is None or spec.kind is not ToolKind.WRITE:
        raise PreEvidenceError(
            f"工具 {event.tool!r} 不是写类工具：动手前取证只对「会把内容写进文件」的动作有意义"
        )

    if event.tool == "edit":
        return _propose_edit(tool_input, event=event, workspace=workspace)

    # write（content）与 str_replace_editor（file_text / new_str）：提案是整份文本。
    # 注意 str_replace_editor 的 new_str 是**片段**，只有 file_text 才是整份内容；
    # 片段要当整份内容用，就得先看 old_str——下面的分支保证不猜。
    if event.tool == "str_replace_editor":
        return _propose_str_replace_editor(tool_input, event=event, workspace=workspace)

    for field in spec.proposed_fields:
        value = tool_input.get(field)
        if isinstance(value, str):
            return _Proposal(content=value, source_field=field, mode="verbatim")
    raise PreEvidenceError(
        f"工具 {event.tool!r} 的提议内容字段缺失："
        f"需要 {list(spec.proposed_fields)} 中至少一个非空字符串"
    )


def _propose_edit(tool_input: Mapping[str, Any], *, event: PolicyEvent, workspace: Path) -> _Proposal:
    old = tool_input.get("old_string")
    new = tool_input.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str):
        raise PreEvidenceError("edit 需要 old_string 与 new_string 两个字符串参数")
    original = _read_current(workspace, event.file)
    return _Proposal(
        content=_apply_replacement(original, old, new, field="old_string"),
        source_field="new_string",
        mode="replacement",
    )


def _propose_str_replace_editor(
    tool_input: Mapping[str, Any], *, event: PolicyEvent, workspace: Path
) -> _Proposal:
    file_text = tool_input.get("file_text")
    if isinstance(file_text, str):
        return _Proposal(content=file_text, source_field="file_text", mode="verbatim")
    key = "str_replace_editor"
    old = tool_input.get("old_str")
    new = tool_input.get("new_str")
    if isinstance(old, str) and isinstance(new, str):
        original = _read_current(workspace, event.file)
        return _Proposal(
            content=_apply_replacement(original, old, new, field="old_str"),
            source_field="new_str",
            mode="replacement",
        )
    raise PreEvidenceError(
        f"{key} 的提议内容无法重建：需要 file_text（整份写入）"
        "或 old_str + new_str（字面量替换）这一组字段；缺失时无法证明改动后的内容"
    )


def _apply_replacement(original: str, old: str, new: str, *, field: str) -> str:
    """字面量替换：`old` 必须**恰好出现一次**，否则拒绝。"""

    if not old:
        raise PreEvidenceError(f"tool_input.{field} 为空串：空锚点的替换范围无法证明，拒绝取证")
    count = original.count(old)
    if count != 1:
        raise PreEvidenceError(
            f"tool_input.{field} 在目标文件里出现 {count} 次（必须恰好 1 次）："
            "无法证明这次改动之后文件是什么内容，因此拒绝在证明不了的情况下放行"
            + (
                "；载荷声明了 replace_all=true，而本实现只承认唯一匹配——"
                "替换范围证明不了时不猜"
                if count > 1
                else ""
            )
        )
    return original.replace(old, new, 1)


def _read_current(workspace: Path, repo_path: str) -> str:
    target = workspace / repo_path
    try:
        data = target.read_bytes()
    except OSError as error:
        raise PreEvidenceError(
            f"读不到目标文件 {repo_path}（{type(error).__name__}）："
            "字面量替换的基准内容证明不了"
        ) from error
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PreEvidenceError(
            f"目标文件 {repo_path} 不是 UTF-8 文本：无法证明改动之后的内容"
        ) from error


# --------------------------------------------------------------------------- 影子工作区


def _relative(path: Path, root: Path) -> str:
    """仓库相对路径（POSIX 分隔符）；等于根目录时返回空串。"""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):  # pragma: no cover - os.walk 只会给出 root 之下的路径
        return path.as_posix()


def _excluded(relative: str, exclude: Sequence[str]) -> bool:
    """仓库相对路径是否命中排除 glob。

    目录要按"名字"与"名字 + /"两种写法各试一次：仓库既有的 glob 语义里 "**/" 匹配
    **零个或多个**目录（src/validators/globs.py，与 adapter 的实现一致），
    所以 ".git/**" 命中 ".git/" 而不命中 ".git"。只试一种写法会让"排除 .git"变成
    "排除它下面的文件、但照样走进去"——对目录剪枝来说等于没排除。
    """

    with_slash = relative + "/"
    return any(
        glob_match(pattern, relative) or glob_match(pattern, with_slash) for pattern in exclude
    )


def _copy_workspace(source: Path, target: Path, *, exclude: Sequence[str], shadow_root: Path) -> int:
    """把工作区复制成影子副本，只复制未被 exclude 命中的内容，返回复制了多少个文件。

    两个必须剪枝的东西：

    - 命中 exclude 的目录/文件（数据声明，可评审）；
    - **影子目录自己**：默认 shadow_root 就在项目里（`<project>/.policy/pre-evidence`），
      不剪就会把自己复制进自己，递归到磁盘满。
    """

    copied = 0
    shadow = shadow_root.resolve()
    for dirpath, dirnames, filenames in os.walk(source):
        here = Path(dirpath)
        relative_dir = _relative(here, source)
        kept: list[str] = []
        for name in sorted(dirnames):
            child = here / name
            child_relative = f"{relative_dir}/{name}" if relative_dir else name
            if _excluded(child_relative, exclude):
                continue
            try:
                if child.resolve() == shadow or shadow.is_relative_to(child.resolve()):
                    continue
            except OSError:  # pragma: no cover - 解析不了的目录按"不剪"处理，代价只是一次多余遍历
                pass
            kept.append(name)
        dirnames[:] = kept

        destination = target if not relative_dir else target / relative_dir
        destination.mkdir(parents=True, exist_ok=True)
        for name in sorted(filenames):
            relative = f"{relative_dir}/{name}" if relative_dir else name
            if _excluded(relative, exclude):
                continue
            candidate = here / name
            if not candidate.is_file():  # 断链的符号链接不是文件，复制它会失败
                continue
            shutil.copy2(candidate, destination / name)
            copied += 1
    return copied


def _write_proposal(shadow: Path, repo_path: str, content: str) -> None:
    """把提议内容写进影子副本（目标文件不存在时按 write 的语义创建它）。"""

    target = shadow / repo_path
    try:
        target.resolve().relative_to(shadow.resolve())
    except ValueError as error:
        raise PreEvidenceError(f"提议目标 {repo_path} 逃出了影子工作区：拒绝写入") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" ：不做换行翻译。dsh 写的是工具参数里的那个字符串，
    # 影子副本必须逐字节等于它，否则验证器验的是另一份内容。
    target.write_text(content, encoding="utf-8", newline="")


def _assert_shadow_is_disposable(*, workspace: Path, shadow: Path) -> None:
    """影子目录必须"删掉它不会碰到被治理项目"。

    这条检查是**数据安全**级别：影子副本在 finally 里会被整棵删除。只要 shadow 等于
    被治理项目、或是它的祖先，`rmtree` 删掉的就是项目本身——声明里写错一个 "." 或
    一个 ".." 就能造成不可逆的损失。今天这条路径要靠"影子目录名恰好等于项目目录名"
    才可能触发（名字里带动作标识的哈希），但这正是那种"将来改一次命名规则就静默变成
    可触发"的检查：宁可在取证之前拒绝，也不要在 finally 里赌。
    """

    project = Path(workspace).resolve()
    resolved = Path(shadow).resolve()
    if resolved == project or project.is_relative_to(resolved):
        raise PreEvidenceError(
            "影子目录与被治理项目重叠（影子等于项目，或项目在影子之内）："
            "副本用完会被整棵删除，这种声明会删掉项目本身，拒绝取证"
        )


def _shadow_name(event: PolicyEvent) -> str:
    """影子目录名：动作标识（可读）+ 短哈希（唯一）。

    动作标识里带 ":"（session:tool_use），不能直接当路径段；截断到一定长度是为了让
    路径总长可控，截断之后可能撞名，所以再拼 8 位哈希——它同时保证"同一个动作"
    每次得到同一个目录名，残留判断因此是确定的。
    """

    raw = event.event_id or event.request_id
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:48].strip("._-") or "action"
    return f"{safe}-{sha256(raw.encode('utf-8')).hexdigest()[:8]}"


# --------------------------------------------------------------------------- 取证树的形状（P3）


def _tree_digest(shadow: Path) -> str:
    """影子树的指纹：仓库相对路径 + 文件 sha256，按稳定顺序覆盖。

    实现只有一份：`provenance.worktree.evidence_tree_digest`（方案 §3.1「四个名字、一份实现」）。
    这里显式用**标注模式**（strict=False）：Phase 5 的取证摘要把指纹当标注用，读不到的副本
    不该让整个判定变成 evidence_unavailable；封条路径一律走默认的严格模式——两种口径是
    同一个函数的显式参数，不是两份实现。
    """

    return evidence_tree_digest(shadow, strict=False).sha256


def _describe_tree(
    *,
    shadow: Path,
    target_existed_before: bool,
    proposal: _Proposal,
    anchor: Path,
) -> Mapping[str, Any]:
    """影子树的形状 → 进审计的脱敏摘要（只标注，不改判定）。

    files_copied 不在这里重复造：它是既有的顶层键，就是这棵树复制了多少个文件。
    """

    tree: dict[str, Any] = {
        "scope": TREE_SCOPE,
        "target_existed_before": target_existed_before,
        "tree_digest": _tree_digest(shadow),
        "note": TREE_NOTE,
    }
    gaps = _tree_gaps(shadow, proposal=proposal, anchor=anchor)
    if gaps is not None:
        # 只在"真的查过"时写这个键：没有它 = 这次没做（平台数据读不到 / 提议内容解析不了），
        # 而不是"查过、没有缺口"。
        tree["tree_gaps"] = gaps
    return tree


def _tree_gaps(
    shadow: Path, *, proposal: _Proposal, anchor: Path
) -> Optional[Mapping[str, Any]]:
    """可选标注：提议内容里"看起来是项目内、但树里找不到"的模块。

    口径是**可能漏、不误报**：只在"顶层包已经存在于影子树里、但这个模块的文件/包目录
    找不到"时报出——这正是 P3 里 isort 把项目内模块判成第三方的形状。顶层包都不在树里的
    import 一律不报（它可能是第三方，也可能只是还没写）。

    数据（validation/project.yaml 的 python_roots）读不到、或提议内容解析不了时**不写这个
    键**："没做"与"做了、没发现"必须能分开读。它只标注树缺什么，绝不参与判定。
    """

    try:
        # 与 _run_validators 同样的函数内导入：没声明 pre_evidence 的部署不该因为
        # "验证器层读不到"而连 Hook 都起不来。
        from validators.depgraph import build_module_index
        from validators.python_ast import parse_module
        from validators.registry import load_config as load_validation_config

        profile = load_validation_config(root=anchor).project
        facts = parse_module(proposal.content)
        if not facts.ok:
            # 连语法都不成立：能说的只有"没做"，不编一份空的缺口清单出来
            return None
        index = build_module_index(shadow, profile)
    except Exception:  # noqa: BLE001 - 加分项：算不出来就不写这个键，绝不因此让取证失败
        return None

    unresolved: set[str] = set()
    for fact in facts.imports:
        module = fact.module
        if fact.level > 0 or not module:
            continue  # 相对导入由 depgraph 按包展开，不是"项目内模块不见了"这一类
        if fact.dynamic and not fact.constant:
            continue  # 动态 import 的目标不是常量：那是"解析不了"，不是"树里没有"
        if index.modules.get(module) is not None:
            continue
        if module.split(".")[0] not in index.top_levels:
            continue
        unresolved.add(module)
    return {
        "status": "checked",
        "python_roots": [str(root) for root in profile.python_roots],
        "unresolved_project_modules": sorted(unresolved),
        "note": TREE_GAPS_NOTE,
    }


# --------------------------------------------------------------------------- 平台数据与流水线


def _registry_anchor(registry_root: Path) -> Tuple[Path, str]:
    """把声明出来的 registry_root 解析成 `validators.registry.load_config(root=...)` 的锚点。

    两种写法都收，因为声明方关心的其实是"平台数据在哪"：

    - 指向**包含** `validation/` 的那一层（仓库根）：原样当锚点，resolution="as_declared"；
    - 指向 `validation/` 目录本身（adapter 配置的测试口径）：锚点取它的父目录，
      resolution="parent_of_declared"。

    两种形状同时成立时**报错**而不是挑一个：配置有歧义时挑一个，就等于把"读的是哪份数据"
    变成猜的（AGENTS 第 3 条）。解析方式写进摘要，读数的人不必去猜。
    """

    as_declared = registry_root / "validation" / "validators.yaml"
    as_parent = registry_root / "validators.yaml"
    if as_declared.is_file() and as_parent.is_file():
        raise PreEvidenceError(
            "pre_evidence.registry_root 有歧义：同时存在 "
            "<root>/validation/validators.yaml 与 <root>/validators.yaml；"
            "请声明**包含 validation/ 的那一层**"
        )
    if as_declared.is_file():
        return registry_root, "as_declared"
    if as_parent.is_file():
        return registry_root.parent, "parent_of_declared"
    raise PreEvidenceError(
        "pre_evidence.registry_root 下找不到平台验证器数据（需要其中的 "
        "validation/validators.yaml，或本身就是那个 validation/ 目录）："
        "没有数据就没有证据，拒绝在证明不了的情况下放行"
    )


def _run_validators(
    *,
    pre: Any,
    anchor: Path,
    event: PolicyEvent,
    context: PolicyContext,
    rules: RuleSet,
    shadow: Path,
) -> Any:
    """跑真实流水线。

    只在这里 import validators：没声明 pre_evidence 的部署不该因为"验证器层读不到"
    而连 Hook 都起不来（起不来 = 非 0 非 2 退出 = dsh 侧放行）。
    """

    from validators.pipeline import PipelineRequest, run_pipeline
    from validators.registry import load_config as load_validation_config

    validation = load_validation_config(root=anchor)
    request = PipelineRequest(
        target=event.file,
        workspace=shadow,
        context=context,
        rules=rules,
        changed_files=(event.file,),
        only=pre.validators,
    )
    return run_pipeline(request, config=validation)


def _summary(
    report: Any,
    *,
    bundle: EvidenceBundle,
    pre: Any,
    resolution: str,
    proposal: _Proposal,
    files_copied: int,
    repo_path: str,
    tree: Mapping[str, Any],
) -> Mapping[str, Any]:
    """审计用的脱敏摘要：验证器怎么跑成、证据覆盖了哪些 checker、目标内容是哪一份。

    target.file 记的是**仓库相对路径**（本次动作要写的那个文件），不是流水线在影子副本里
    用的绝对路径：审计要回答「这次查的是哪个文件」，而影子路径既含本机目录（会被脱敏成
    <abs>，于是读数的人看不到文件名），又随副本落点变化、不可复现。
    """

    target = report.target
    payload = {
        "status": "collected",
        # 声明是怎么解析的：读账本的人不该靠猜 registry_root 指的是哪一层
        "registry_resolution": resolution,
        "validators_requested": list(pre.validators),
        "checks": list(report.checks),
        # P2：语言维度的显式判定（有 rule pack / 按声明不取证 / 语言未知）。形状由
        # validators.pipeline 冻结（键固定 language / status / reason / declared_in），
        # 这里原样搬进审计——否则"这次的语言按声明不取证"只存在于流水线报告里，
        # 账本读不到，而 07 §4 P2 要的正是"这件事能从账本读到"。
        "language_coverage": dict(report.language_coverage),
        "served_checkers": list(report.served_checkers),
        "validators": [
            {
                "id": record.validator,
                "status": record.status.value,
                "critical": record.critical,
                "evidence_count": record.evidence_count,
                "reason": record.reason,
            }
            for record in report.validators
        ],
        "judgements": [dict(item.to_payload()) for item in report.judgements],
        # Q7：这次的树还在构建中（测试已落地、它 import 的项目内模块/名字还没有）。
        # 它必须能从账本读到，否则"这次写入是在覆盖测试跑不了的状态下放行的"只能靠
        # 读 allow 反推——而那正是"跳过被当成通过"的老毛病。
        "pending_implementation": [
            dict(item.to_payload()) for item in report.pending_implementation
        ],
        "pending_implementation_note": PENDING_IMPLEMENTATION_NOTE,
        "blockers": [dict(item.to_payload()) for item in report.blockers],
        "target": None
        if target is None
        else {
            "file": repo_path,
            "language": target.language,
            "sha256": target.sha256,
            "bytes": target.bytes,
            "lines": target.lines,
        },
        "target_sha256": None if target is None else target.sha256,
        "proposal": {
            "field": proposal.source_field,
            "mode": proposal.mode,
            "chars": len(proposal.content),
            "sha256": "sha256:" + sha256(proposal.content.encode("utf-8")).hexdigest(),
        },
        "evidence_count": len(bundle.evidence),
        "dependencies": sorted({fact.name for fact in bundle.dependencies}),
        "unmapped_findings": report.unmapped_findings,
        "truncated_evidence": report.truncated_evidence,
        "files_copied": files_copied,
        # P3：这条证据属于哪棵树（范围 / 目标是否预先存在 / 树指纹 / 缺口）。
        # 它只标注"读数的人该知道的事"，判定一个字都没改。
        "tree": dict(tree),
    }
    return _redact(payload)
