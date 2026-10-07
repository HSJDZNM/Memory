# AB-5 臂运行时与净化树：把「控制臂真的读不到规则」变成一条命令就能证明的事。
#
# 用法::
#
#     python tools/ab_arm.py --list-sanitization            # 净化面（每条带理由）
#     python tools/ab_arm.py --materialize --baseline-fixture shop --out .tmp/ab-arms
#     python tools/ab_arm.py --assert-clean --run-dir .tmp/ab-arms/<run>
#     python tools/ab_arm.py --self-proof                   # 变异自证：故意留规则 -> 断言必须红 -> 撤回 -> 绿
#     python tools/ab_arm.py --run --task demo-1 --path src/shop/order_controller.py \
#         --old "from service import OrderService" --new "from repository import OrderRepository" --arm all
#     python tools/ab_arm.py --run ... --dsh                # 额外尝试 dsh 端到端（本机可能起不来，见下）
#
# 退出码（与仓库既有工具同型）::
#
#     0 = 全部成功（断言绿 + 每个臂按各自语义收场）
#     1 = 有失败（断言红 / 该拦的没拦 / 该过的没过 / 想证明的读数取不到）
#     2 = 用法或配置错误（参数缺失、基线树不存在、净化清单为空）
#
# 三臂的语义（**判定不是自造的**）
# ==============================
#
#   off       不跑治理：改动一律应用。**没有 entry**，所以也不该有任何判定记录。
#   advisory  判定**照样来自真实入口**（同一条 dsh Hook 命令、同一份 adapter 配置），
#             但臂**不执行阻断动作**：记录判定与诊断，改动仍然应用。
#             "advisory 与 enforced 只有执行动作不同"这件事本身是判据：两者的 decision 必须逐字相等。
#   enforced  判定来自真实入口；decision=block 时**不应用**改动，且被拒时树逐字节不变。
#
# 真实入口的降级阶梯（**绝不自造判定路径**）
# ========================================
#
#   1. dsh-plugin：dsh --profile headless --patch <patch> "任务"（真实产品路径，用进程内插件转发）；
#   2. dsh-hook-cli：python -m adapters.dsh.hooks --config ... --hooks-config ... --audit ...
#      —— 这是 dsh 在真实接线里**逐字执行的那条命令**（见 examples/dsh/hooks.json 与
#      tools/dsh_sandbox_loop.py 的 HOOK_COMMAND），喂真实 PreToolUse 载荷；
#   3. 没有第 3 条。判定逻辑只有 policy.engine.evaluate 一条路径，本文件一行都不复制。
#
#   降级要写清弱在哪：hook-cli 走的是同一条命令、同一份配置、同一份判定，弱的是**外层**——
#   没有 dsh 的工具管线，所以"dsh 有没有把 Hook 的 deny 传到管线"这一段没有被覆盖
#   （src/adapters/dsh/README.md 第 7 节实测过：外部命令桥在本机不阻断，进程内插件才阻断）。
#   被拒的判据必须是**两条同时成立**：audit.jsonl 里有一条 block，且目标文件哈希不变。
#   只有其一 = unavailable（"跑不了"绝不被读成"拦住了"）。
#
# 净化面（**路径删 + 内容扫 + 规则库在树外**，三件一起才算干净）
# ==========================================================
#
#   只删路径不够：规则可以被间接复述；只扫内容不够：编码过的规则扫不出来。
#   所以 --assert-clean 同时要求：清单路径不存在、内容扫描零命中、rules_root 在臂树之外。
#   清单与理由见 SANITIZATION；自证见 --self-proof（AGENTS 第 45 条：仪器必须证明自己会红）。
#
# 基线从哪来（`--baseline` 只收**外部任务树**）
# ==========================================
#
#   --baseline-fixture shop   生成固定夹具项目（最小三层树 + 一个自带测试）；
#   --baseline <dir>          任意外部 checkout（任务树）。
#
#   **平台仓库自己不是受支持的基线。** clean 判据问的是"这棵臂树里能不能读到平台自己的规则集
#   与产物"，而平台仓库必然在自己的**追溯语料**里引用规则 ID（docs/project/rule-effects/**、
#   docs/project/reviews/** 就是逐条点评规则的报告）。拿它当基线时 clean 段报红，说明的是
#   **你在问一个不该问的问题**——不是扫描器误报，也不是净化清单漏了东西。平台自测请用
#   --baseline-fixture；外部任务树的判定才是这套读数的适用范围。
#
# 不承诺什么
# ==========
##   - 净化不覆盖 .git 历史：本工具复制时就**不带 .git**（复制忽略项里有它），
#     但基线树里若已有别的历史副本（例如打包好的 zip），它管不着；这一点写在 --list-sanitization 的 note 里；
#   - 内容扫描只认"规则身份形态"的正则，认不出的复述（中文意译、改名后的 YAML）它抓不到——
#     所以清单以**路径**为主、正则为辅，抓不到的部分如实写成缺口；
#   - 本工具不测"平台有没有效"（那是 AB-1/AB-2 的事），它只保证**臂是干净且可复算的**。

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from provenance import reading_context as reading  # noqa: E402

# 本载荷自己的协议轴（AGENTS 第 55 条）。1.0 = 首次建轴。
AB_ARM_SCHEMA_VERSION = "1.0"
# 给 ab_measure.py 的输入清单自己的轴（与上面那条各走各的：一个是本次运行，一个是交接面）。
MEASUREMENT_INPUT_SCHEMA_VERSION = "1.0"

DEFAULT_OUT = ".tmp/ab-arms"
DEFAULT_TASK = "synthetic-edit"

ARM_OFF = "off"
ARM_ADVISORY = "advisory"
ARM_ENFORCED = "enforced"
ARMS = (ARM_OFF, ARM_ADVISORY, ARM_ENFORCED)

ENTRY_NONE = "none"
ENTRY_DSH_PLUGIN = "dsh-plugin"
ENTRY_DSH_HOOK_CLI = "dsh-hook-cli"

ACTION_APPLIED = "applied"
ACTION_REFUSED = "refused"
ACTION_NOT_GOVERNED = "not_governed"

DECISION_NOT_GOVERNED = "not_governed"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

# 复制基线树时忽略的东西：构建产物与版本库历史（**不带 .git 是有意的**：
# 带着它，臂树里 git log / git show HEAD:policies/... 就能把规则读回来，净化等于没做）。
COPY_IGNORE = (
    ".git",
    ".tmp",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".uv-cache",
)


#: 「这棵树就是平台仓库自己」的特征**组合**：单看任何一条都会误伤（外部任务树也可能带 policies/），
#: 三条同时成立才算——规则本体 + 核心判定引擎 + 本机门禁。
PLATFORM_REPO_FEATURES: tuple[str, ...] = (
    "policies/*/*.yaml（规则本体）",
    "src/policy/engine.py（核心判定引擎）",
    "tools/ci_local.py（本机门禁）",
)


def platform_repo_features(tree: Path) -> list[str]:
    """基线树命中了哪几条「平台仓库自己」的特征。"""

    hits: list[str] = []
    if any((tree / "policies").glob("*/*.yaml")):
        hits.append(PLATFORM_REPO_FEATURES[0])
    if (tree / "src" / "policy" / "engine.py").is_file():
        hits.append(PLATFORM_REPO_FEATURES[1])
    if (tree / "tools" / "ci_local.py").is_file():
        hits.append(PLATFORM_REPO_FEATURES[2])
    return hits


def assert_supported_baseline(baseline: Path) -> None:
    """`--baseline` 只收**外部任务树**；平台仓库自己按用法错误拒绝（退出码 2）。

    clean 判据问的是「这棵臂树里能不能读到平台自己的规则集与产物」。平台仓库必然在自己的
    追溯语料里引用规则 ID（docs/project/rule-effects/**、docs/project/reviews/**），此时 clean
    段报红是**在问一个不该问的问题**——所以不受支持的输入要在这里失败关闭，而不是产出一份
    让人误以为是缺陷的读数。判据是**特征组合**（三条同时成立），不是单一路径：外部任务树
    带一份 policies/ 是正常的。
    """

    hits = platform_repo_features(baseline)
    if len(hits) == len(PLATFORM_REPO_FEATURES):
        raise UsageError(
            "基线树看起来就是平台仓库自己（命中：" + "；".join(hits) + "）。"
            "`--baseline` 的输入是**外部任务树**：clean 判据问的是「这棵臂树里能不能读到平台自己的"
            "规则集与产物」，而平台仓库必然在追溯语料里引用规则 ID（docs/project/rule-effects/**、"
            "docs/project/reviews/**），此时报红是在问一个不该问的问题，不是缺陷。"
            "平台自测请用 --baseline-fixture shop。"
        )


class UsageError(Exception):
    """用法 / 配置错误：退出码 2。"""


@dataclass(frozen=True)
class SanitizedPath:
    """一条净化项：路径形态 + 为什么它必须被删。"""

    pattern: str
    reason: str
    added_by: str = "task-15 任务书"


# 净化清单（数据在这里，理由逐条可评审）。
# 任务书写死的那几条我原样保留，另外补的被标成"自查新增"。
SANITIZATION: tuple[SanitizedPath, ...] = (
    SanitizedPath("policies/**", "规则本体（43 条规则 YAML，含码与严重级别）"),
    SanitizedPath("AGENTS.md", "含大量规则 ID、判定口径与核心约束"),
    SanitizedPath("validation/**", "ruff.toml 的 select 表 + 码归属注释 + validators.yaml（treatment 的一部分）"),
    SanitizedPath("knowledge/**", "corpus.yaml 里的 rule_sources 登记（规则 -> 出处）"),
    SanitizedPath("docs/project/engineering-policy-platform/**", "方案与门槛：含 GV 口径、规则清单、预注册预测"),
    SanitizedPath(
        "docs/project/architecture/**",
        "自查新增：规则转化覆盖报告逐条点评 43 条规则（原文就是一份规则清单）",
    ),
    SanitizedPath(
        "docs/mirrors/**",
        "自查新增：规则的上游原文——读得到镜像就能把规则反推出来",
    ),
    SanitizedPath(
        "tests/fixtures/rules/**",
        "自查新增：每条规则的正反例夹具（文件名即规则 ID）",
    ),
    SanitizedPath(
        "tests/fixtures/decisions/**",
        "自查新增：决策协议快照里带 rule_id / message / severity",
    ),
    SanitizedPath(
        "evaluation/**",
        "自查新增：门槛、语料锁与读数里带规则清单、码与逐规则 P/R",
    ),
    SanitizedPath(
        "registry/**",
        "自查新增：受控工具表与已审核哈希——不是规则，但泄露「哪些动作被治理」= treatment 边界",
    ),
    SanitizedPath("examples/dsh/**", "自查新增：钩子接线与 adapter 配置（treatment 的接线面）"),
    SanitizedPath(".dsh/**", "钩子配置目录（存在就删）"),
    SanitizedPath(".policy/**", "钩子配置 / 审计 / 台账（存在就删；臂运行时自己生成自己的）"),
)

# 内容扫描：规则身份。
# 局限写在这里：它只认**本平台自己的规则 ID**与几个明显的键名，
# **认不出**中文意译、改名后的 YAML、或把规则编码进别的东西里——所以清单以路径为主。
RULE_ID_SHAPE_PATTERN: tuple[str, str] = (
    r"\b[A-Z][A-Z0-9]{1,9}-\d{1,4}\b",
    "规则身份形态（兜底：policies/ 读不到时才用；UTF-8 / SHA-256 / AB-5 这类标准写法也会命中）",
)

#: 判定协议 / 审计记录里的键名：改名后的 YAML 认不出，但这几个键名一出现就是协议形态的泄露。
PROTOCOL_KEY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brule_id\b", "判定协议里的 rule_id 键名"),
    (r"\bmatched_rules\b", "判定协议里的 matched_rules 键名"),
    (r"\bskipped_rules\b", "判定协议里的 skipped_rules 键名"),
    (r"\bviolations_by_severity\b", "审计记录里的按级别分布键名"),
)

#: 扫描器**自己的源文件**：它必然包含模式串、载荷键名与自证植入的规则 ID。
#: 把这几样当成"泄露"，会让一棵真正干净的臂树永远报 dirty（实测：只放这一个文件的树上命中 15 行）。
SELF_SOURCE = "tools/ab_arm.py"


def rule_identities(root: Path | None = None) -> tuple[str, ...]:
    """本平台自己的规则 ID：policies/<domain>/<ID>.yaml 的文件名主干。

    这是"规则身份"的**权威集合**——比"大写字母组-数字"的形态串精确得多：
    UTF-8 / SHA-256 / ISO-8601 / R16-4 这些标准写法与章节号都不在其中。
    读不到（没有 policies/ 目录）就返回空元组，由调用方回退到形态串并**在读数里说明**。
    """

    base = (root or REPO_ROOT) / "policies"
    if not base.is_dir():
        return ()
    identities: list[str] = []
    for path in sorted(base.glob("*/*.yaml")):
        value = path.stem.strip()
        if value and value not in identities:
            identities.append(value)
    return tuple(identities)


def leak_patterns(root: Path | None = None) -> tuple[tuple[str, str], ...]:
    """本次真正使用的扫描模式：规则 ID（优先取权威集合） + 协议键名。"""

    identities = rule_identities(root)
    if identities:
        head = (
            (
                r"\b(?:" + "|".join(re.escape(item) for item in identities) + r")\b",
                "本平台规则 ID（%d 条，取自 policies/*/*.yaml）" % len(identities),
            ),
        )
    else:
        head = (RULE_ID_SHAPE_PATTERN,)
    return head + PROTOCOL_KEY_PATTERNS

# 内容扫描只扫这些后缀（其余当二进制跳过）
TEXT_SUFFIXES = {
    ".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".toml", ".ini", ".cfg", ".txt",
    ".mjs", ".js", ".ts", ".ps1", ".sh", ".bat", ".html", ".css", ".rst", ".ipynb",
}

HOOK_MODULE = "adapters.dsh.hooks"
VERDICT_PREFIX = "[policy] VERDICT "

PATCH_TEMPLATE = """# 由 tools/ab_arm.py 生成：把进程内策略 Hook 插件挂到 profile 上。
- insert:
    - id: policy-hook
      name: '{plugin}'
      config:
        command: '{command}'
        timeoutMs: {timeout_ms}
        projectDir: '{project}'
"""

ADAPTER_CONFIG = """# 由 tools/ab_arm.py 生成：受治理项目的 dsh Adapter 配置。
# rules_root / rules 指向**臂树之外**的规则库——净化的是臂树，治理照样读得到规则。
agent_version: "{agent_version}"
project: {project}
project_root: ..
rules:
  - {rules_root}/policies
rules_root: {rules_root}
timeout_ms: 5000
layers:
  - pattern: "**/*_controller.py"
    layer: controller
  - pattern: "**/*_service.py"
    layer: service
  - pattern: "**/*_repository.py"
    layer: repository
languages:
  - pattern: "**/*.py"
    language: python
default_language: text
audit_log: {audit_log}
principal:
  subject: local-user
  roles:
    - developer
registry: {rules_root}/registry/tool-registry.yaml
registry_approved: {rules_root}/registry/tool-registry.approved.json
enforcement_ledger: {ledger}
"""


def display(path: Path | str | None) -> str:
    return reading.display_path(path, root=REPO_ROOT)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))



# --------------------------------------------------------------------------- 组装一次 run


PRESETS: Mapping[str, Mapping[str, Any]] = {
    "blocked": {
        "task_id": "blocked-dependency",
        "tool": "edit",
        "path": "src/shop/order_controller.py",
        "old": "from shop.order_service import OrderService",
        "new": "from shop.order_repository import OrderRepository",
        "expect": "enforced 应拒（同一条编辑在 advisory 通过）",
    },
    "allowed": {
        "task_id": "allowed-method",
        "tool": "edit",
        "path": "src/shop/order_controller.py",
        "old": "    def create(self, payload: dict) -> dict:\n        return self.service.create(payload)",
        "new": (
            "    def create(self, payload: dict) -> dict:\n        return self.service.create(payload)\n\n"
            "    def ping(self) -> str:\n        return \"pong\""
        ),
        "expect": "两臂都应通过（治理不该拦合规改动）",
    },
}


def prepare_arm(*, baseline: Path, arm_dir: Path, arm: str, rules_root: Path) -> Mapping[str, Any]:
    tree = arm_dir / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    arm_dir.mkdir(parents=True, exist_ok=True)
    copy_baseline(baseline, tree)
    removed = sanitize_tree(tree)
    seeded = seed_shop(tree)
    manifest = {
        "arm": arm,
        "tree": display(tree),
        "rules_root": rules_root.as_posix(),
        "sanitization": removed,
        "seeded_fixture": seeded,
        "kept_note": (
            "tests/ 只删了 fixtures/rules 与 fixtures/decisions 两处；其余保留，"
            "否则可用性 oracle 就没有可跑的测试了（删了什么逐条在 sanitization 里）"
        ),
    }
    write_json(arm_dir / "arm.json", manifest)
    return manifest


def run_one(
    *,
    baseline: Path,
    out_root: Path,
    run_id: str,
    arm: str,
    preset: str,
    target: Optional[str],
    old: Optional[str],
    new: Optional[str],
    content: Optional[str],
    tool: Optional[str],
    use_dsh: bool,
    oracle_python: str,
    pass_to_pass: Sequence[str],
    fail_to_pass: Sequence[str],
    oracle_timeout_s: int,
) -> Mapping[str, Any]:
    started_at = reading.utc_now()
    spec = dict(PRESETS.get(preset or "", {}))
    task_id = str(spec.get("task_id") or (target or DEFAULT_TASK))
    path = target or spec.get("path")
    if path is None:
        raise UsageError("--path 缺失：非 preset 调用必须显式给出要改的文件")
    old_value = old if old is not None else spec.get("old")
    new_value = new if new is not None else spec.get("new")
    if content is None and new_value is None:
        raise UsageError("--new 或 --content 必须给一个（否则没有提议内容可测）")
    tool_name = tool or str(spec.get("tool") or ("edit" if content is None else "write"))

    run_dir = Path(out_root) / run_id
    arm_dir = run_dir / arm
    unavailable: list[Mapping[str, str]] = []
    manifest = prepare_arm(baseline=baseline, arm_dir=arm_dir, arm=arm, rules_root=REPO_ROOT)
    tree = arm_dir / "tree"

    cleanliness = assert_clean(arm_dir)
    if not cleanliness["clean"]:
        unavailable.append({"what": "assert_clean", "reason": "; ".join(cleanliness["problems"])})

    # 提议的写动作（**工具调用由本工具构造**；判定由真实入口做）
    if tool_name == "edit":
        tool_input: dict[str, Any] = {"file_path": path, "old_string": old_value or "", "new_string": new_value or ""}
        proposed = {"kind": "edit", "path": path, "old_string": old_value, "new_string": new_value, "content": None}
    else:
        tool_input = {"file_path": path, "file_text": content if content is not None else (new_value or "")}
        proposed = {
            "kind": "write",
            "path": path,
            "old_string": None,
            "new_string": None,
            "content": content if content is not None else (new_value or ""),
        }
        new_value = None

    before_dir = arm_dir / "tree-before"
    before_dir.mkdir(parents=True, exist_ok=True)
    target_before = tree / path
    before_sha = sha256_file(target_before)
    if target_before.is_file():
        copy_target = before_dir / path
        copy_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target_before, copy_target)
    write_json(
        before_dir / "note.json",
        {
            "note": (
                "tree-before 里只放**本次写动作触碰的文件**（全树副本没必要也慢）；"
                "整棵臂树的读数看 arm_tree_digest 与 baseline_tree 的逐文件哈希"
            ),
            "files": [path] if target_before.is_file() else [],
        },
    )
    baseline_sha = sha256_file(baseline / path)

    entry: Mapping[str, Any]
    execution: dict[str, Any] = {}
    decision = DECISION_NOT_GOVERNED
    action = ACTION_NOT_GOVERNED
    if arm == ARM_OFF:
        entry = {"kind": ENTRY_NONE, "real": False, "argv": [], "fallback_reason": None, "side_effect_free": True}
    else:
        payload = hook_payload(
            tool_name=tool_name,
            tool_input=tool_input,
            cwd=tree,
            call_id=run_id + "-" + arm + "-1",
            session="ab-arm-" + run_id,
        )
        fallback_reason = None
        if use_dsh:
            attempt = run_dsh_plugin(arm_dir=arm_dir, tree=tree, prompt="用 " + tool_name + " 工具改 " + path + "，然后一句话报告结果。")
            if not attempt.get("ok"):
                fallback_reason = "dsh 端到端不可用：" + str(attempt.get("reason"))
            else:
                fallback_reason = "dsh 端到端跑过（见 execution.dsh），但判定读数仍以同一条 Hook 命令为准（可复核）"
                execution["dsh"] = {
                    "argv": attempt.get("argv"),
                    "exit_code": attempt.get("exit_code"),
                    "wall_ms": attempt.get("wall_ms"),
                    "stdout_tail": (attempt.get("stdout") or "")[-600:],
                    "stderr_tail": (attempt.get("stderr") or "")[-600:],
                }
        hook = run_hook_cli(arm_dir=arm_dir, tree=tree, payload=payload)
        entry = {
            "kind": ENTRY_DSH_HOOK_CLI,
            "real": True,
            "argv": hook["argv"],
            "fallback_reason": fallback_reason,
            # 入口**有副作用**：它按设计写审计与台账（arm_dir/.policy 下）。照实写 false，
            # 让 ab_measure 自己决定要不要重复跑；重复跑必须每次一棵新臂树（否则第二次起命中幂等台账）。
            "side_effect_free": False,
            "side_effect_note": "写 arm_dir/.policy/audit.jsonl 与 enforcement-ledger.jsonl；不改臂树源码",
            "repeat_semantics": "每次重复必须是一次新的 --run（新的臂树），否则第二次起会命中幂等台账变成 event_replay",
        }
        if hook["error"]:
            unavailable.append({"what": "entry", "reason": hook["error"]})
        execution.update(
            {
                "exit_code": hook["exit_code"],
                "wall_ms": hook["wall_ms"],
                "stdout_tail": hook["stdout"][-800:],
                "stderr_tail": hook["stderr"][-800:],
            }
        )
        if hook["exit_code"] == 0:
            decision = "allow"
        elif hook["exit_code"] == 2:
            decision = "block"
        else:
            decision = "unavailable"
            unavailable.append(
                {"what": "entry", "reason": "退出码 " + str(hook["exit_code"]) + "：既不是放行也不是阻断"}
            )

    if arm == ARM_ENFORCED and decision == "block":
        action = ACTION_REFUSED
    else:
        action = ACTION_APPLIED
        applied = apply_edit(tree=tree, path=path, old=old_value, new=new_value, content=content)
        if not applied["applied"]:
            unavailable.append({"what": "apply", "reason": str(applied["detail"])})
            action = "apply_failed"
        execution["apply_detail"] = applied["detail"]

    after_sha = sha256_file(tree / path)
    records, audit_error = read_audit(arm_dir / ".policy" / "audit.jsonl")
    if arm != ARM_OFF and audit_error:
        unavailable.append({"what": "audit", "reason": audit_error})
    audit = audit_summary(records)
    if arm == ARM_ENFORCED and decision == "block":
        # 判据：被拒必须**两条同时成立**（audit 里有 block + 文件哈希不变）。缺一 = unavailable。
        if not audit["has_block"]:
            unavailable.append({"what": "block_evidence", "reason": "decision=block 但审计里没有 block 记录"})
        if after_sha != before_sha:
            unavailable.append({"what": "block_evidence", "reason": "decision=block 但文件哈希变了（没真拦住）"})

    oracle = run_oracle(
        tree=tree,
        arm_dir=arm_dir,
        python=oracle_python,
        node_ids=list(pass_to_pass) + list(fail_to_pass),
        timeout_s=oracle_timeout_s,
    )
    write_json(arm_dir / "oracle.json", oracle)

    declared_changed = [path]
    changed = [path] if after_sha != before_sha else []
    digest_tree = tree_digest(tree)
    run_payload = {
        "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
        "run_id": run_id,
        "arm": arm,
        "task_id": task_id,
        "preset": preset or None,
        "expect": spec.get("expect"),
        "baseline": {"path": display(baseline), "digest": sha256_file(baseline)},
        "sanitization": {"profile": "default", "removed": manifest["sanitization"], "seeded_fixture": manifest["seeded_fixture"], "kept_note": manifest["kept_note"]},
        "arm_tree": {"path": display(tree), "digest": digest_tree, "clean": cleanliness["clean"]},
        "rules_root": {"path": display(REPO_ROOT), "inside_arm_tree": cleanliness["rules_root"]["inside_arm_tree"]},
        "entry": dict(entry),
        "execution": {
            **execution,
            "decision": decision,
            "enforced_action": action,
            "file_changed": after_sha != before_sha,
            "file_sha256_before": before_sha,
            "file_sha256_after": after_sha,
        },
        "audit": {**audit, "ref": display(arm_dir / ".policy" / "audit.jsonl")},
        # 环境断言 L1–L5（ab-protocol §4.3）。L4 是**装置自检**：控制臂不许看到 [policy] 标记，
        # treatment 臂必须看到——看不到就说明"处理"根本没施加，那时任何对照都不成立。
        "leak_assertions": leak_assertions(
            arm=arm,
            tree=tree,
            stdout=str(execution.get("stdout_tail") or ""),
            stderr=str(execution.get("stderr_tail") or ""),
        ),
        # 只做到"树级隔离"：本工具不建文件系统命名空间，也不清理宿主 .dsh 接线里的既有配置。
        # 记成 tree_only 而不是 fs_isolated——**不许默认成更强的那一档**。
        "isolation_level": "tree_only",
        "oracle": oracle,
        "unavailable": [dict(item) for item in unavailable],
        "reading_context": reading_context_payload(
            run_id=run_id,
            started_at=started_at,
            declarations={
                "arm_config": reading.declaration_block(arm_dir / ".policy" / "dsh-adapter.yaml", root=REPO_ROOT)
                if (arm_dir / ".policy" / "dsh-adapter.yaml").is_file()
                else reading.not_applicable(),
                "sanitization_note": {"status": "available", "items": len(SANITIZATION), "source": "tools/ab_arm.py::SANITIZATION"},
            },
        ),
        "timestamp": reading.utc_now(),
    }
    write_json(arm_dir / "run.json", run_payload)
    write_json(
        arm_dir / "verdict.json",
        {
            "available": arm != ARM_OFF,
            "entry_kind": entry["kind"],
            "decision": decision,
            "exit_code": execution.get("exit_code"),
            "stderr_tail": execution.get("stderr_tail"),
        },
    )
    write_json(
        arm_dir / "changes.json",
        {
            "declared_changed_files": declared_changed,
            "changed_files": changed,
            "file_sha256_before": before_sha,
            "baseline_sha256": baseline_sha,
            "file_sha256_after": after_sha,
        },
    )
    measurement = {
        "schema_version": MEASUREMENT_INPUT_SCHEMA_VERSION,
        "task_id": task_id,
        "arm": arm,
        "run_dir": display(arm_dir),
        "baseline_tree": display(baseline),
        "arm_tree": display(tree),
        "arm_tree_digest": digest_tree,
        "tree_before": display(before_dir),
        "tree_after": display(tree),
        "tree_before_note": "只含本次写动作触碰的文件（全树副本没必要）；整树比对用 baseline_tree vs arm_tree",
        "declared_changed_files": declared_changed,
        "changed_files": changed,
        "proposed_edits": [{"action_id": run_id + "-" + arm + "-1", **proposed}],
        "governance": {
            "entry_kind": entry["kind"],
            "entry_argv": list(entry.get("argv") or []),
            "entry_side_effect_free": entry.get("side_effect_free"),
            "decision": decision,
            "enforced_action": action,
            "blocked": decision == "block",
            "diagnostic_count": len(records),
            "violations_by_severity": {},
            "verdict_ref": "verdict.json",
            "audit_ref": "audit.jsonl",
        },
        "timing": {"wall_ms": execution.get("wall_ms"), "entry_wall_ms": execution.get("wall_ms"), "stages": []},
        "counts": {
            "role": "manipulation_check",
            "role_note": (
                "本工具的计数是**装置自检**（三臂的构造差异读得出来），不是结局变量："
                "off 臂 governed_write_actions=0 是构造出来的，不是测出来的"
            ),
            "write_actions": 1 if action in (ACTION_APPLIED, "apply_failed") else 0,
            "governed_write_actions": 1 if (arm != ARM_OFF and action in (ACTION_APPLIED, ACTION_REFUSED, "apply_failed")) else 0,
            "bypass_actions": 0,
            "human_interventions": 0,
            "retries": 0,
            "bypass_definition": (
                "bypass = 写动作没有经过治理入口就落到树上。off 臂恒为 0（构造上没有治理路径）；"
                "advisory/enforced 的每次写动作都先过入口，所以也是 0；"
                "非 0 只可能来自「入口没跑成但改动仍然应用」——那种情况记 action=apply_failed + unavailable，不记 0-1 计数"
            ),
        },
        "oracle": {
            "python": oracle_python,
            "test_command": {"argv": oracle.get("argv"), "cwd": display(tree), "timeout_s": oracle_timeout_s, "env": {"PYTHONPATH": display(tree / "src")}},
            "test_select_style": "append_node_ids",
            "pass_to_pass": list(pass_to_pass),
            "fail_to_pass": list(fail_to_pass),
            "result": oracle,
        },
        "unavailable": [dict(item) for item in unavailable],
    }
    write_json(arm_dir / "measurement_input.json", measurement)
    return {"run": run_payload, "measurement": measurement, "arm_dir": arm_dir}


def tree_digest(tree: Path) -> str:
    """整棵臂树的稳定摘要：只覆盖「相对路径 + 文件哈希」，与 reading_context 的 tree 块同型。"""

    _, files = walk_relative(tree)
    payload = chr(10).join(
        relative + ":" + (sha256_file(tree / relative) or "unreadable") for relative in files
    )
    return "sha256:" + sha256_bytes(payload.encode("utf-8"))


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ab_arm.py",
        description="AB-5 臂运行时：生成净化臂树、跑真实入口、把一次 run 的产物写成可复算的读数。",
    )
    parser.add_argument("--list-sanitization", action="store_true", help="列出净化面与理由")
    parser.add_argument("--self-proof", action="store_true", help="变异自证：断言必须会红")
    parser.add_argument("--materialize", action="store_true", help="只生成三臂净化树，不跑任务")
    parser.add_argument("--run", action="store_true", help="跑一次任务（三臂或指定臂）")
    parser.add_argument("--assert-clean", action="store_true", help="对已生成的臂断言净化")
    parser.add_argument(
        "--probe-platform-path",
        action="store_true",
        help="正向对照：探针**故意**把平台挂上 PYTHONPATH——断言此时必须红（证明探针真的在探）",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="外部任务树的基线。**平台仓库自己不是受支持的基线**（clean 判据问的是这棵臂树能不能"
             "读到平台自己的规则集与产物，而平台仓库必然在追溯语料里引用规则 ID）——检出这种输入"
             "直接按用法错误拒绝（exit 2）；平台自测用 --baseline-fixture。不给基线且不用夹具时"
             "同样是用法错误，没有"默认仓库自己"这回事",
    )
    parser.add_argument(
        "--baseline-fixture",
        default=None,
        metavar="NAME",
        help="用内置固定夹具项目当基线（树锚在平台之外，避免「删 6 条路径就打坏 oracle」那条死路）",
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="产物根目录（默认 .tmp/ab-arms）")
    parser.add_argument("--run-id", default=None, help="本次运行的 id；不给就按 UTC 时间戳生成")
    parser.add_argument("--run-dir", default=None, help="已生成的运行目录（--assert-clean 用）")
    parser.add_argument("--arm", default="all", help="off | advisory | enforced | all")
    parser.add_argument("--preset", default=None, help="blocked | allowed（内置最小任务）")
    parser.add_argument("--task", default=None, help="任务 id（不给就取 preset 的）")
    parser.add_argument("--path", default=None, help="要改的文件（相对臂树）")
    parser.add_argument("--old", default=None, help="edit 的 old_string")
    parser.add_argument("--new", default=None, help="edit 的 new_string")
    parser.add_argument("--content", default=None, help="write 的完整内容")
    parser.add_argument("--tool", default=None, help="工具名（默认 edit / 给了 --content 则 write）")
    parser.add_argument("--dsh", action="store_true", help="额外尝试 dsh 端到端（本机可能起不来）")
    parser.add_argument("--oracle-python", default=sys.executable, help="跑可用性 oracle 的解释器")
    parser.add_argument("--pass-to-pass", action="append", default=[], help="可用性 oracle 的 node id（可重复）")
    parser.add_argument("--fail-to-pass", action="append", default=[], help="可用性 oracle 的 node id（可重复）")
    parser.add_argument("--oracle-timeout-s", type=int, default=600, help="oracle 超时（秒）")
    parser.add_argument("--json", action="store_true", help="打印完整载荷")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    if args.baseline_fixture:
        baseline: Path | None = build_fixture_baseline(args.baseline_fixture, out_root)
        if not args.pass_to_pass and not args.fail_to_pass:
            args.pass_to_pass = list(FIXTURE_NODE_IDS)
    elif args.baseline:
        baseline = Path(args.baseline)
        if not baseline.is_absolute():
            baseline = (REPO_ROOT / baseline).resolve()
    else:
        baseline = None  # 只有不需要基线的动作（--list-sanitization / --assert-clean）允许为空
    run_id = args.run_id or (utc_stamp() + "-" + uuid.uuid4().hex[:6])

    def require_baseline(resolved: Path | None) -> Path:
        """用基线的动作统一走这里：缺基线 / 不受支持的基线都在这里失败关闭。"""

        if resolved is None:
            raise UsageError(
                "缺基线：给 --baseline-fixture <name>（夹具项目，例如 shop）或 --baseline <外部任务树>"
            )
        assert_supported_baseline(resolved)
        return resolved

    try:
        if args.list_sanitization:
            payload = {
                "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
                "kind": "sanitization",
                "items": [
                    {"pattern": item.pattern, "reason": item.reason, "added_by": item.added_by}
                    for item in SANITIZATION
                ],
                "leak_patterns": [{"regex": pattern, "label": label} for pattern, label in leak_patterns()],
                "copy_ignore": list(COPY_IGNORE),
                "kept": "tests/ 只删 fixtures/rules 与 fixtures/decisions；其余保留（可用性 oracle 要用）",
                "limits": (
                    "路径删除是主判据、内容扫描是兜底：中文意译、改名后的 YAML、编码过的规则扫描抓不到；"
                    "复制不带 .git，所以臂树里没有版本库历史可查"
                ),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_sanitization(payload))
            return EXIT_OK

        if args.self_proof:
            current = require_baseline(baseline)
            if not current.is_dir():
                raise UsageError("基线树不存在：" + display(current))
            payload = self_proof(baseline=current, out_root=out_root)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_self_proof(payload))
            return EXIT_OK if payload["result"] == "pass" else EXIT_FAIL

        if args.assert_clean:
            run_dir = Path(args.run_dir or (out_root / run_id))
            if not run_dir.is_absolute():
                run_dir = REPO_ROOT / run_dir
            arms = ARMS if args.arm == "all" else (args.arm,)
            results = []
            for arm in arms:
                if not (run_dir / arm).is_dir():
                    continue
                results.append(assert_clean(run_dir / arm, probe_platform_path=bool(args.probe_platform_path)))
            if not results:
                raise UsageError("在 " + display(run_dir) + " 下没有找到任何臂目录")
            clean = all(item["clean"] for item in results)
            payload = {
                "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
                "kind": "assert-clean",
                "run_dir": display(run_dir),
                "arms": results,
                "clean": clean,
                "timestamp": reading.utc_now(),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_clean(payload))
            return EXIT_OK if clean else EXIT_FAIL

        if args.materialize:
            current = require_baseline(baseline)
            if not current.is_dir():
                raise UsageError("基线树不存在：" + display(current))
            run_dir = out_root / run_id
            arms = ARMS if args.arm == "all" else (args.arm,)
            manifests = {}
            for arm in arms:
                manifests[arm] = prepare_arm(baseline=current, arm_dir=run_dir / arm, arm=arm, rules_root=REPO_ROOT)
            payload = {
                "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
                "kind": "materialize",
                "run_id": run_id,
                "run_dir": display(run_dir),
                "baseline": display(current),
                "arms": {arm: {"tree": manifest["tree"], "removed": len(manifest["sanitization"]), "seeded": manifest["seeded_fixture"]} for arm, manifest in manifests.items()},
                "timestamp": reading.utc_now(),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_materialize(payload))
            return EXIT_OK

        if args.run:
            current = require_baseline(baseline)
            if not current.is_dir():
                raise UsageError("基线树不存在：" + display(current))
            if args.preset and args.preset not in PRESETS:
                raise UsageError("未知 preset " + repr(args.preset) + "；有 " + " / ".join(sorted(PRESETS)))
            arms = ARMS if args.arm == "all" else (args.arm,)
            if args.arm != "all" and args.arm not in ARMS:
                raise UsageError("未知臂 " + repr(args.arm) + "；有 " + " / ".join(ARMS))
            outputs = []
            for arm in arms:
                outputs.append(
                    run_one(
                        baseline=current,
                        out_root=out_root,
                        run_id=run_id,
                        arm=arm,
                        preset=args.preset,
                        target=args.path,
                        old=args.old,
                        new=args.new,
                        content=args.content,
                        tool=args.tool,
                        use_dsh=bool(args.dsh),
                        oracle_python=args.oracle_python,
                        pass_to_pass=list(args.pass_to_pass),
                        fail_to_pass=list(args.fail_to_pass),
                        oracle_timeout_s=args.oracle_timeout_s,
                    )
                )
            payload = {
                "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
                "kind": "run",
                "run_id": run_id,
                "run_dir": display(out_root / run_id),
                "results": [item["measurement"] for item in outputs],
                "runs": [item["run"] for item in outputs],
                "timestamp": reading.utc_now(),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_run(payload))
            failed = any(item["run"]["execution"]["enforced_action"] == "apply_failed" or item["run"]["unavailable"] for item in outputs)
            return EXIT_FAIL if failed else EXIT_OK

        raise UsageError("没有动作：用 --list-sanitization / --self-proof / --materialize / --assert-clean / --run 之一")
    except UsageError as error:
        print("用法错误：" + str(error), file=sys.stderr)
        return EXIT_USAGE


# --------------------------------------------------------------------------- 渲染


def render_sanitization(payload: Mapping[str, Any]) -> str:
    lines = ["净化面（%d 条）：" % len(payload["items"])]
    for item in payload["items"]:
        lines.append("  " + item["pattern"].ljust(46) + item["reason"])
    lines.append("")
    lines.append("内容扫描（兜底）：" + ", ".join(item["regex"] for item in payload["leak_patterns"]))
    lines.append("保留：" + payload["kept"])
    lines.append("局限：" + payload["limits"])
    return chr(10).join(lines)


def render_self_proof(payload: Mapping[str, Any]) -> str:
    lines = ["变异自证 | " + str(payload["result"]) + " | 仪器会红=" + str(payload["instrument_goes_red"])]
    for verdict in payload["verdicts"]:
        lines.append(
            "  " + verdict["stage"].ljust(18)
            + " 期望 clean=" + str(verdict["expected_clean"]).ljust(5)
            + " 实测 clean=" + str(verdict["observed_clean"]).ljust(5)
            + " 符合=" + str(verdict["as_expected"])
        )
    lines.append("artifact: " + str(payload["run_dir"]) + "/self-proof.json")
    return chr(10).join(lines)


def render_clean(payload: Mapping[str, Any]) -> str:
    lines = ["净化断言 | clean=" + str(payload["clean"]) + " | " + str(payload["run_dir"])]
    for arm in payload["arms"]:
        lines.append(
            "  " + str(arm["arm"]).ljust(9) + " clean=" + str(arm["clean"]).ljust(5)
            + " 扫描=" + str(arm["leak_scan"]["scanned_files"]) + " 文件 命中=" + str(arm["leak_scan"]["hit_count"])
            + " rules_root 在树内=" + str(arm["rules_root"]["inside_arm_tree"])
        )
        for problem in arm["problems"]:
            lines.append("      ! " + problem)
    return chr(10).join(lines)


def render_materialize(payload: Mapping[str, Any]) -> str:
    lines = ["已生成三臂净化树 | " + str(payload["run_dir"]) + " | 基线 " + str(payload["baseline"])]
    for arm, item in payload["arms"].items():
        lines.append("  " + arm.ljust(9) + " 删除 " + str(item["removed"]) + " 项，seed " + str(len(item["seeded"])) + " 个文件")
    return chr(10).join(lines)


def render_run(payload: Mapping[str, Any]) -> str:
    lines = ["臂运行时 | run=" + str(payload["run_id"]) + " | " + str(payload["run_dir"])]
    for item in payload["results"]:
        governance = item["governance"]
        lines.append(
            "  " + str(item["arm"]).ljust(9)
            + " entry=" + str(governance["entry_kind"]).ljust(13)
            + " decision=" + str(governance["decision"]).ljust(11)
            + " action=" + str(governance["enforced_action"]).ljust(11)
            + " file_changed=" + str(item["changed_files"] != []).ljust(5)
            + " wall_ms=" + str(item["timing"]["wall_ms"])
        )
        for problem in item["unavailable"]:
            lines.append("      ! UNAVAILABLE " + str(problem["what"]) + ": " + str(problem["reason"])[:160])
    lines.append("每次 run 的产物：" + " / ".join(name for name in ("run.json", "verdict.json", "audit.jsonl", "changes.json", "measurement_input.json", "oracle.json")))
    return chr(10).join(lines)


# --------------------------------------------------------------------------- 净化：复制 / 删除 / 扫


def matches_pattern(relative: str, pattern: str) -> bool:
    """路径是否命中净化项；支持 dir/** 与精确文件两种形态。"""

    from fnmatch import fnmatch

    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return relative == prefix or relative.startswith(prefix + "/")
    return fnmatch(relative, pattern)


def copy_baseline(baseline: Path, target: Path) -> None:
    """复制基线树；不带 .git / .tmp / 缓存（**不带 .git 是有意的**，见模块 docstring）。"""

    shutil.copytree(
        baseline,
        target,
        ignore=shutil.ignore_patterns(*COPY_IGNORE),
        symlinks=True,
    )


def walk_relative(root: Path) -> Tuple[list[str], list[str]]:
    """返回 (目录相对路径, 文件相对路径)，都是 POSIX 形态且升序。"""

    dirs: list[str] = []
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            dirs.append(relative)
        elif path.is_file():
            files.append(relative)
    return dirs, files


def sanitize_tree(tree: Path) -> list[Mapping[str, Any]]:
    """按 SANITIZATION 删除路径；返回逐条记录（路径 + 理由 + 类型）。"""

    dirs, files = walk_relative(tree)
    removed: list[Mapping[str, Any]] = []
    handled: set[str] = set()
    for item in SANITIZATION:
        candidates = [
            relative
            for relative in (dirs + files)
            if matches_pattern(relative, item.pattern)
            and not any(relative.startswith(parent + "/") for parent in handled)
        ]
        for relative in sorted(candidates):
            target = tree / relative
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            except OSError as error:
                removed.append(
                    {
                        "path": relative,
                        "pattern": item.pattern,
                        "reason": item.reason,
                        "kind": "dir" if relative in set(dirs) else "file",
                        "removed": False,
                        "error": type(error).__name__ + ": " + str(error),
                    }
                )
                continue
            handled.add(relative)
            removed.append(
                {
                    "path": relative,
                    "pattern": item.pattern,
                    "reason": item.reason,
                    "kind": "dir" if relative in set(dirs) else "file",
                    "removed": True,
                }
            )
    return removed


def missing_sanitization_paths(tree: Path) -> list[Mapping[str, Any]]:
    """清单里哪些项在树里**还能找到**（= 没删干净）。"""

    dirs, files = walk_relative(tree)
    present = dirs + files
    leftovers: list[Mapping[str, Any]] = []
    for item in SANITIZATION:
        hits = [relative for relative in present if matches_pattern(relative, item.pattern)]
        if hits:
            leftovers.append({"pattern": item.pattern, "reason": item.reason, "hits": hits[:20], "count": len(hits)})
    return leftovers


def leak_scan(tree: Path) -> Mapping[str, Any]:
    """内容扫描：规则身份形态的正则命中。

    局限（照实写）：只认形态串与几个键名，认不出中文意译或改名后的 YAML；
    所以它是**兜底**，主判据是路径删除。扫过的文件数与跳过数都要报出来。
    """

    patterns = leak_patterns()
    compiled = [(re.compile(pattern), label) for pattern, label in patterns]
    hits: list[Mapping[str, Any]] = []
    scanned = 0
    skipped = 0
    _, files = walk_relative(tree)
    for relative in files:
        path = tree / relative
        if path.suffix.lower() not in TEXT_SUFFIXES:
            skipped += 1
            continue
        if relative == SELF_SOURCE:
            # 扫描器自己的声明不算证据：它写着模式串、载荷键名，还写着自证要植入的规则 ID。
            skipped += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), start=1):
            for regex, label in compiled:
                match = regex.search(line)
                if match:
                    hits.append(
                        {"path": relative, "line": number, "pattern": label, "match": match.group(0)[:80]}
                    )
                    break
    return {
        "scanned_files": scanned,
        "skipped_files": skipped,
        "hits": hits[:100],
        # 两个单位都给（r3 提的口径问题）：hit_count = **命中行数**（每行只记第一个命中的模式，
        # 命中即 break），files_with_hits = **不同文件数**。只报一个数就会与别人的读数不可比。
        "hit_count": len(hits),
        "files_with_hits": len({item["path"] for item in hits}),
        "hit_unit": "lines（每行首个命中模式，命中即 break）",
        "scan_root": display(tree),
        "excludes": (
            "只排除扫描器自己的源文件 " + SELF_SOURCE
            + "（它必然包含模式串、载荷键名与自证植入的规则 ID）；其余不排除"
        ),
        "suffix_filter": sorted(TEXT_SUFFIXES),
        "patterns": [{"regex": pattern, "label": label} for pattern, label in patterns],
        "limits": (
            "只认本平台规则 ID 与几个协议键名；中文意译 / 改名后的 YAML / 编码过的规则它抓不到"
            "（主判据是路径删除）"
        ),
    }


RUNTIME_PROBE = (
    "import json;"
    "from policy.check import repo_root;"
    "from policy.loader import load_rule_set;"
    "root=repo_root();"
    "rules=load_rule_set([root/'policies'], repo_root=root);"
    "print(json.dumps({'repo_root': str(root), 'rule_set_hash': rules.identity, 'rule_count': len(rules.rules)}))"
)


def runtime_probe(tree: Path, *, with_platform_path: bool = False) -> Mapping[str, Any]:
    """运行时探针：**从任务树里**问一句"我够不够得着平台"。

    为什么需要它（lead 2026-10-07 裁定 + r3 实测）：净化是**路径删除，不是可达性控制**。
    在本仓副本路线上，删掉 policies/ 之后，policy.check 的 repo_root() 会从被检查文件向上回溯，
    照样加载 43 条规则（r3 用两种 PYTHONPATH 都复现）。所以"树里没有 policies/"证明不了
    "任务树没被治理"——必须用行为证据。
    """

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if with_platform_path:
        env["PYTHONPATH"] = str(SRC_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", RUNTIME_PROBE],
            cwd=str(tree), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"reachable": None, "reason": type(error).__name__ + ": " + str(error), "with_platform_path": with_platform_path}
    if completed.returncode != 0:
        return {
            "reachable": False,
            "with_platform_path": with_platform_path,
            "reason": (completed.stderr or "").strip().splitlines()[-1][:200] if completed.stderr else "probe 退出码非 0",
        }
    try:
        facts = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as error:
        return {"reachable": None, "reason": "probe 输出无法解析：" + str(error), "with_platform_path": with_platform_path}
    return {
        "reachable": True,
        "with_platform_path": with_platform_path,
        "repo_root": display(Path(str(facts.get("repo_root")))),
        "rule_set_hash": facts.get("rule_set_hash"),
        "rule_count": facts.get("rule_count"),
    }


def assert_clean(arm_dir: Path, *, probe_platform_path: bool = False) -> Mapping[str, Any]:
    """三件一起才算干净：清单路径不存在 + 内容扫描零命中 + rules_root 在臂树之外。"""

    manifest_path = arm_dir / "arm.json"
    if not manifest_path.is_file():
        raise UsageError("找不到 " + display(manifest_path) + "：这个目录不是 ab_arm 生成的臂")
    manifest = read_json(manifest_path)
    tree = arm_dir / "tree"
    if not tree.is_dir():
        raise UsageError("臂树不存在：" + display(tree))
    problems: list[str] = []
    # 裁据（lead 2026-10-07 + ab-protocol §4.1）：断言只有两条——
    #   ① 任务树里不存在平台产物；② 平台检出不在任务树内。
    # 那 6 条路径不是"必须没有的 6 个路径"，而是"平台产物"这个概念的**可操作化**：
    # 目标树锚在平台之外时它们本来就一个都不存在；锚在本仓副本上时才需要删，而那条路
    # 结构性不可比（oracle 与 treatment 抢 tests/**），所以它降级成一条**证伪断言**。
    bootstrap_route = (tree / "policies").is_dir() or (tree / "AGENTS.md").is_file() or (tree / "validation").is_dir()
    leftovers = missing_sanitization_paths(tree)
    for item in leftovers:
        problems.append("净化不彻底：" + item["pattern"] + " 还能找到 " + str(item["count"]) + " 个路径")
    scan = leak_scan(tree)
    if scan["hit_count"]:
        problems.append("内容扫描命中 " + str(scan["hit_count"]) + " 处规则身份形态")
    rules_root = Path(manifest.get("rules_root") or "")
    inside = None
    if rules_root.parts:
        try:
            resolved_root = rules_root.resolve()
            resolved_tree = tree.resolve()
            inside = resolved_root == resolved_tree or resolved_tree in resolved_root.parents
        except (OSError, ValueError):
            inside = None
    else:
        problems.append("manifest 里没有 rules_root：无法证明规则库在臂树之外")
    if inside:
        problems.append("rules_root 落在臂树之内：净化等于没做")
    probe = runtime_probe(tree, with_platform_path=probe_platform_path)
    probe_claim = {
        "claim": "运行时探针：从任务树里够不着平台（净化是路径删除，不是可达性控制，所以必须用行为证据）",
        "reachable": probe.get("reachable"),
        "detail": dict(probe),
        "status": "pass" if probe.get("reachable") is False else ("fail" if probe.get("reachable") else "unavailable"),
    }
    if probe_claim["status"] == "fail":
        problems.append("运行时探针够得着平台：加载到了 " + str(probe.get("rule_count")) + " 条规则（" + str(probe.get("rule_set_hash"))[:24] + "）")
    vcs_dir = (tree / ".git").exists()
    vcs_block = {
        "claim": "任务树里没有版本库目录（**只对自举路线成立**：clone + git rm 之后 "
                 "git show HEAD:policies/<ID>.yaml 仍读得到规则，r3 已实测）",
        "role": "falsification_of_bootstrap_route",
        "applicable": bootstrap_route,
        "git_dir_exists": vcs_dir,
        "status": ("fail" if vcs_dir else "pass") if bootstrap_route else "not_applicable",
    }
    return {
        "arm": manifest.get("arm"),
        "tree": display(tree),
        "clean": not problems,
        "problems": problems,
        "route": "bootstrap_repo_copy" if bootstrap_route else "external_task_tree",
        "claims": {
            "no_platform_artifacts_in_task_tree": not leftovers,
            "platform_checkout_outside_task_tree": inside is False,
            "runtime_probe_cannot_reach_platform": probe.get("reachable") is False,
        },
        "runtime_probe": probe_claim,
        "vcs_dir_absent": vcs_block,
        "sanitization_leftovers": leftovers,
        "leak_scan": scan,
        "rules_root": {"path": display(rules_root) if rules_root.parts else None, "inside_arm_tree": inside},
    }


# --------------------------------------------------------------------------- 臂运行时


SHOP_FIXTURE: Mapping[str, str] = {
    "src/shop/order_controller.py": '''"""订单 HTTP 入口。"""

from service import OrderService


class OrderController:
    def __init__(self) -> None:
        self.service = OrderService()

    def create(self, payload: dict) -> dict:
        return self.service.create(payload)
''',
    "src/shop/order_service.py": '''"""订单业务逻辑。"""

from repository import OrderRepository


class OrderService:
    def __init__(self) -> None:
        self.repository = OrderRepository()

    def create(self, payload: dict) -> dict:
        return self.repository.insert(payload)
''',
}


def seed_shop(tree: Path) -> list[str]:
    """把最小受控项目写进臂树（与 tools/dsh_sandbox_loop.py 的 demo-shop 同型）。

    为什么要 seed：任务书要的对照是"**同一条编辑**在 advisory 通过、在 enforced 被拒"。
    这条编辑必须落在一个平台真的会判定的对象上——分层来自 adapter 配置的 glob
    （**/*_controller.py -> controller），依赖来自变更文本里的 import。
    """

    written = []
    for relative, text in sorted(SHOP_FIXTURE.items()):
        target = tree / relative
        if target.exists():
            # **不覆盖**基线里已有的文件：夹具基线自带的 controller 是能导入的（可用性 oracle 的
            # pass_to_pass 就挂在它上面），覆盖成沙箱版会把 oracle 打坏，读数就变成噪声。
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline=chr(10))
        written.append(relative)
    return written


def hook_payload(*, tool_name: str, tool_input: Mapping[str, Any], cwd: Path, call_id: str, session: str) -> Mapping[str, Any]:
    """真实 PreToolUse 载荷的形状（与 tools/dsh_sandbox_loop.py / agent_loop.py 同型）。"""

    return {
        "session_id": session,
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": dict(tool_input),
        "tool_use_id": call_id,
    }


def write_hook_configs(*, arm_dir: Path, tree: Path, rules_root: Path) -> Mapping[str, Path]:
    """写 adapter 配置 / hooks.json / patch.yml；审计与台账放在**臂树之外**的 arm_dir 下。"""

    policy = arm_dir / ".policy"
    policy.mkdir(parents=True, exist_ok=True)
    audit = policy / "audit.jsonl"
    ledger = policy / "enforcement-ledger.jsonl"
    adapter = policy / "dsh-adapter.yaml"
    hooks = policy / "hooks.json"
    adapter.write_text(
        ADAPTER_CONFIG.format(
            agent_version=agent_version(),
            project=tree.name,
            rules_root=rules_root.as_posix(),
            audit_log=audit.as_posix(),
            ledger=ledger.as_posix(),
        ),
        encoding="utf-8",
        newline=chr(10),
    )
    command = (
        "python -m " + HOOK_MODULE + " --config " + adapter.as_posix()
        + " --hooks-config " + hooks.as_posix() + " --audit " + audit.as_posix()
    )
    hooks.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": command, "timeout": 30}]}]}},
            ensure_ascii=False,
            indent=2,
        )
        + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    patch = policy / "patch.yml"
    patch.write_text(
        PATCH_TEMPLATE.format(
            plugin=(REPO_ROOT / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs").as_posix(),
            command=command,
            timeout_ms=30000,
            project=tree.as_posix(),
        ),
        encoding="utf-8",
        newline=chr(10),
    )
    return {"adapter": adapter, "hooks": hooks, "audit": audit, "ledger": ledger, "patch": patch, "command": command}


def tool_env() -> Mapping[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_hook_cli(*, arm_dir: Path, tree: Path, payload: Mapping[str, Any], timeout_s: int = 60) -> Mapping[str, Any]:
    """跑 dsh 在真实接线里逐字执行的那条命令（不是自造入口）。"""

    configs = write_hook_configs(arm_dir=arm_dir, tree=tree, rules_root=REPO_ROOT)
    argv = [
        sys.executable,
        "-m",
        HOOK_MODULE,
        "--config",
        str(configs["adapter"]),
        "--hooks-config",
        str(configs["hooks"]),
        "--audit",
        str(configs["audit"]),
    ]
    started = time.time()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(tree),
            env=tool_env(),
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "kind": ENTRY_DSH_HOOK_CLI,
            "argv": argv,
            "exit_code": None,
            "wall_ms": int((time.time() - started) * 1000),
            "stdout": "",
            "stderr": "",
            "error": type(error).__name__ + ": " + str(error),
            "configs": configs,
        }
    return {
        "kind": ENTRY_DSH_HOOK_CLI,
        "argv": argv,
        "exit_code": completed.returncode,
        "wall_ms": int((time.time() - started) * 1000),
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "error": None,
        "configs": configs,
    }


def run_dsh_plugin(*, arm_dir: Path, tree: Path, prompt: str, timeout_s: int = 300) -> Mapping[str, Any]:
    """真实产品路径：dsh --profile headless --patch <patch.yml> "任务"。

    本机受限沙箱下 Hook 可能起不来（spawn EPERM，见 src/adapters/dsh/README.md 第 7.1 节）；
    起不来时**不当作拦住**，由调用方降级到 hook-cli 并把原因写进 fallback_reason。
    """

    which = shutil.which("dsh") or shutil.which("dsh.cmd")
    if which is None:
        return {"ok": False, "reason": "PATH 上没有 dsh 可执行文件"}
    configs = write_hook_configs(arm_dir=arm_dir, tree=tree, rules_root=REPO_ROOT)
    argv = [which, "--profile", "headless", "--patch", str(configs["patch"]), prompt]
    started = time.time()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(tree),
            env=tool_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "ok": False,
            "reason": "dsh 起不来：" + type(error).__name__ + ": " + str(error),
            "argv": argv,
            "wall_ms": int((time.time() - started) * 1000),
        }
    return {
        "ok": True,
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "wall_ms": int((time.time() - started) * 1000),
    }


def read_audit(path: Path) -> Tuple[list[Mapping[str, Any]], Optional[str]]:
    """读审计 JSONL；读不到返回 (空, 原因)，**不把读不到当成"没有记录"**。"""

    if not path.is_file():
        return [], "审计文件不存在：" + display(path)
    records: list[Mapping[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as error:
        return records, "审计读取失败：" + type(error).__name__ + ": " + str(error)
    return records, None


def audit_summary(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    decisions = [str(item.get("decision")) for item in records if item.get("decision")]
    exits = [item.get("exit_code") for item in records if "exit_code" in item]
    return {
        "records": len(records),
        "decisions": decisions,
        "exit_codes": exits,
        "has_block": any(code == 2 for code in exits) or "block" in decisions,
    }


def apply_edit(*, tree: Path, path: str, old: Optional[str], new: Optional[str], content: Optional[str]) -> Mapping[str, Any]:
    """把提议的写动作落到臂树上（工具调用由本工具构造，判定由真实入口做）。"""

    target = tree / path
    if content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline=chr(10))
        return {"applied": True, "detail": "write"}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as error:
        return {"applied": False, "detail": "读不到目标文件：" + type(error).__name__}
    if old is None or old not in text:
        return {"applied": False, "detail": "old_string 在目标文件里找不到（唯一匹配）"}
    if text.count(old) != 1:
        return {"applied": False, "detail": "old_string 不唯一"}
    target.write_text(text.replace(old, new or ""), encoding="utf-8", newline=chr(10))
    return {"applied": True, "detail": "edit"}


def _dotted_node_id(node_id: str) -> str:
    """node id（或 junit 键）→ junit 的 dotted 形式，用来做**精确**比较。

    `tests/test_a.py::TestFoo::test_bar` 与 junit 的 classname+name（`tests.test_a.TestFoo.test_bar`）
    在这套归一化下相等；`tests/test_a.py::test_foo` 与 `tests/test_ab.py::test_foo` 不等。
    """

    text = str(node_id).strip().replace("\\", "/")
    text = text.replace(".py::", "::")
    if text.endswith(".py"):
        text = text[:-3]
    return text.replace("::", ".").replace("/", ".")


def declared_outcomes(node_ids: Sequence[str], outcomes: Mapping[str, str]) -> dict:
    """把 junit 的逐用例结果对齐到声明的 node id：**精确匹配**，不做子串模糊。

    旧实现用「文件主干是不是 name 的子串 + 末段后缀相等」两跳近似：`test_shop.py` 会吃到
    `test_shop_extra.py` 的结果（把别的用例的结论记到声明的那条上）；类作用域的 node id
    （`tests/test_x.py::TestFoo::test_bar`）又永远匹配不上 junit 键，真跑过的用例被记成
    `missing`——两个方向都是读数错误。
    """

    lookup = {_dotted_node_id(name): verdict for name, verdict in outcomes.items()}
    return {node: lookup.get(_dotted_node_id(node), "missing") for node in node_ids}


def run_oracle(*, tree: Path, arm_dir: Path, python: str, node_ids: Sequence[str], timeout_s: int) -> Mapping[str, Any]:
    """可用性 oracle：仓库自带测试在**这次运行之后的树**上还绿不绿。

    口径（与 ab-instruments 议定）：声明的每条 node id 必须在 junit 结果里出现且
    outcome=passed；**声明了却没被收集到 = missing，不算通过**。
    跑不了（解释器缺失 / 沙箱拒 temp / 收集失败）一律 unavailable，绝不写"通过"。
    """

    if not node_ids:
        return {"status": "not_declared", "reason": "本次任务没有声明 pass_to_pass / fail_to_pass 节点"}
    tmp = arm_dir / "pytest-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    junit = arm_dir / "oracle-junit.xml"
    # 臂树可能落在平台仓库之内（.tmp/ 下），pytest 会顺着 cwd 向上找到**平台的 pytest.ini**，
    # 于是 oracle 测的是平台配置而不是这棵树（实测：ImportError + Unknown config option: cache_dir）。
    # 显式给一份空配置 + rootdir，把 oracle 与宿主配置隔开。
    ini = arm_dir / "pytest-oracle.ini"
    ini.write_text("[pytest]" + chr(10), encoding="utf-8", newline=chr(10))
    argv = [
        python, "-m", "pytest", *node_ids,
        "-c", str(ini), "--rootdir", str(tree),
        "-p", "no:cacheprovider", "-q", "--no-header",
        "--basetemp=" + str(tmp), "--junit-xml=" + str(junit),
    ]
    env = tool_env()
    env["PYTHONPATH"] = str(tree / "src") + os.pathsep + env.get("PYTHONPATH", "")
    started = time.time()
    try:
        completed = subprocess.run(
            argv, cwd=str(tree), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "unavailable", "reason": "oracle 起不来：" + type(error).__name__ + ": " + str(error), "argv": argv}
    outcomes: dict[str, str] = {}
    parse_error = None
    if junit.is_file():
        import xml.etree.ElementTree as ET

        try:
            root = ET.parse(junit).getroot()
            for case in root.iter("testcase"):
                name = (case.get("classname") or "").replace(".", "/") + ".py::" + (case.get("name") or "")
                verdict = "passed"
                if case.find("failure") is not None:
                    verdict = "failed"
                elif case.find("error") is not None:
                    verdict = "error"
                elif case.find("skipped") is not None:
                    verdict = "skipped"
                outcomes[name] = verdict
        except ET.ParseError as error:
            parse_error = "junit 解析失败：" + str(error)
    else:
        parse_error = "junit 报告不存在（收集期就失败或解释器不可用）"
    declared = declared_outcomes(node_ids, outcomes)
    status = "unavailable" if parse_error else "ran"
    reason = parse_error
    if status == "ran" and not outcomes:
        # 收集期就失败 / 一个用例都没跑起来：**不能**报成"跑过了但没有这条"。
        status = "unavailable"
        reason = "pytest 没有产出任何 testcase（收集期失败？exit_code=" + str(completed.returncode) + "）"
    return {
        "status": status,
        "reason": reason,
        "argv": argv,
        "exit_code": completed.returncode,
        "wall_ms": int((time.time() - started) * 1000),
        "outcomes": declared,
        "collected": len(outcomes),
        "stdout_tail": (completed.stdout or "")[-1500:],
        "stderr_tail": (completed.stderr or "")[-800:],
    }


# --------------------------------------------------------------------------- 夹具基线（树锚在平台之外）

# ab-protocol §4.1 实测：把净化施加在**平台自己的树**上是结构性不可比的——
# 可用性 oracle 要 tests/**（收集期就会因为 validation/ 没了而 12 个模块报错），
# 而 tests/** 又是最大的泄漏源。所以本工具把"目标树锚在平台之外"做成默认路径：
# 用这个固定夹具项目当基线，平台只以 .policy/ 两个文件 + 树外规则库的形式施加。
FIXTURE_PROJECT: Mapping[str, str] = {
    "README.md": "# fixture-shop（A/B 固定夹具项目）\n\n最小项目：一个 controller / service / repository 三层。\n",
    "src/shop/__init__.py": "",
    "src/shop/order_repository.py": '''"""订单仓储。"""


class OrderRepository:
    def insert(self, payload: dict) -> dict:
        return dict(payload)
''',
    "src/shop/order_service.py": '''"""订单业务逻辑。"""

from shop.order_repository import OrderRepository


class OrderService:
    def __init__(self) -> None:
        self.repository = OrderRepository()

    def create(self, payload: dict) -> dict:
        return self.repository.insert(payload)
''',
    "src/shop/order_controller.py": '''"""订单 HTTP 入口。"""

from shop.order_service import OrderService


class OrderController:
    def __init__(self) -> None:
        self.service = OrderService()

    def create(self, payload: dict) -> dict:
        return self.service.create(payload)
''',
    "tests/test_shop.py": '''"""夹具项目自带的可用性 oracle。"""

from shop.order_controller import OrderController


def test_controller_create() -> None:
    assert OrderController().create({"id": 1}) == {"id": 1}
''',
}

FIXTURE_NODE_IDS = ("tests/test_shop.py::test_controller_create",)


def build_fixture_baseline(name: str, out_root: Path) -> Path:
    """生成固定夹具项目树（幂等：每次先删再写）。"""

    target = Path(out_root) / ("baseline-" + name)
    if target.exists():
        shutil.rmtree(target)
    for relative, text in sorted(FIXTURE_PROJECT.items()):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline=chr(10))
    return target


# --------------------------------------------------------------------------- L1–L5 环境断言


# L5 的针脚集（口径必须与读数一起公布，否则「26 处」与「4 个文件」两个数无法互相印证）。
DSH_WIRING_NEEDLES: tuple[str, ...] = (
    "policy-hook.plugin.mjs",
    "adapters.dsh.hooks",
    "policy.check",
    "policy_hook",
)


def dsh_home_wiring_hits(tree: Path, *, needles: Sequence[str] | None = None) -> Mapping[str, Any]:
    """L5：扫 $USERPROFILE/.dsh 的接线里有没有指向这棵树或平台插件。

    两个单位都报：files_with_hits（**文件数**）与 match_count（**出现次数**）。
    别人换一套针脚量出来的数不同是正常的——所以 needles 原文必须一起进读数。
    """

    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    root = Path(home) / ".dsh" if home else None
    if root is None or not root.is_dir():
        return {"status": "not_applicable", "reason": "宿主没有 .dsh 目录（读不到就是读不到）", "hits": []}
    tokens = tuple(item.lower() for item in (needles if needles is not None else DSH_WIRING_NEEDLES))
    needles_used = (tree.as_posix().lower(), *tokens)
    hits: list[str] = []
    match_count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".yml", ".yaml", ".json", ".js", ".mjs", ".ts"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for needle in needles_used:
            if needle in text:
                match_count += text.count(needle)
                hits.append(display(path))
                break
    return {
        "status": "scanned",
        "root": display(root),
        "hits": hits[:20],
        "hit_count": len(hits),
        "files_with_hits": len(hits),
        "match_count": match_count,
        "needles": list(needles_used),
        "scan_root": display(root),
        "suffix_filter": [".yml", ".yaml", ".json", ".js", ".mjs", ".ts"],
    }


def leak_assertions(
    *,
    arm: str,
    tree: Path,
    stdout: str,
    stderr: str,
) -> list[Mapping[str, Any]]:
    """L1–L5（ab-protocol §4.3）。每条都只有 pass / fail / unavailable 三种，不含"大概"。"""

    _, files = walk_relative(tree)
    policy_inside = any(relative == ".policy" or relative.startswith(".policy/") for relative in files)
    policy_inside = policy_inside or any(relative.startswith(".policy") for relative in files)
    leftovers = missing_sanitization_paths(tree)
    scan = leak_scan(tree)
    marker_seen = "[policy]" in (stdout + stderr)
    expect_marker = arm != ARM_OFF
    wiring = dsh_home_wiring_hits(tree)
    return [
        {
            "id": "L1",
            "claim": "净化清单里的路径在臂树里不存在，且臂树里没有 .policy",
            "status": "pass" if (not leftovers and not policy_inside) else "fail",
            "detail": {"leftovers": [item["pattern"] for item in leftovers], "policy_in_tree": policy_inside},
        },
        {
            "id": "L2",
            "claim": "臂树里没有 .git（禁止 clone+git rm 路线：git show HEAD:policies/... 仍读得到）",
            "status": "pass" if not (tree / ".git").exists() else "fail",
            "detail": {"git_dir_exists": (tree / ".git").exists(), "copy_ignore": list(COPY_IGNORE)},
        },
        {
            "id": "L3",
            "claim": "内容级扫描 0 命中",
            "status": "pass" if scan["hit_count"] == 0 else "fail",
            "detail": {"hits": scan["hit_count"], "scanned": scan["scanned_files"], "examples": scan["hits"][:5]},
        },
        {
            "id": "L4",
            "claim": "运行时行为探针：控制臂看不到 [policy] 标记，treatment 臂必须看得到（装置自检）",
            "status": "pass" if marker_seen == expect_marker else "fail",
            "detail": {"marker_seen": marker_seen, "expected": expect_marker, "arm": arm},
            "role": "manipulation_check",
        },
        {
            "id": "L5",
            "claim": "宿主 .dsh 接线里没有指向这棵树 / 平台插件的配置",
            "status": "pass" if wiring.get("hit_count", 0) == 0 else "fail",
            "detail": dict(wiring),
        },
    ]


# --------------------------------------------------------------------------- 变异自证


def self_proof(*, baseline: Path, out_root: Path) -> Mapping[str, Any]:
    """三段读数：绿 -> 故意留规则后必须红 -> 撤回后必须绿。

    两个变异体各打一类漏洞：
      A) 路径变异：往臂树里放回一个 policies/ARCH-001.yaml —— 只有"路径删除"这一层能挡；
      B) 内容变异：放一个 notes.md，正文里写一条规则身份串 —— 只有"内容扫描"这一层能挡。
    两个变异体**都必须被抓到**；漏一个就算自证失败（那说明仪器会漏报，不是我预期的那件事）。
    """

    run_id = "selfproof-" + utc_stamp() + "-" + uuid.uuid4().hex[:6]
    run_dir = Path(out_root) / run_id
    arm_dir = run_dir / ARM_OFF
    tree = arm_dir / "tree"
    arm_dir.mkdir(parents=True, exist_ok=True)
    copy_baseline(baseline, tree)
    removed = sanitize_tree(tree)
    write_json(
        arm_dir / "arm.json",
        {
            "arm": ARM_OFF,
            "tree": display(tree),
            # 绝对路径：display() 对仓库根会返回 "."，而 Path(".").parts 是空元组，
            # 断言会把它读成"没有 rules_root"（这正是自证第一段误红的成因）。
            "rules_root": REPO_ROOT.as_posix(),
            "sanitization": removed,
            "created_by": "tools/ab_arm.py --self-proof",
        },
    )

    stages: list[Mapping[str, Any]] = []
    stage1 = assert_clean(arm_dir)
    stages.append({"stage": "clean", "expect": "clean", "observed": stage1["clean"], "detail": stage1})

    planted_path = tree / "policies" / "ARCH-001.yaml"
    planted_path.parent.mkdir(parents=True, exist_ok=True)
    planted_path.write_text(
        "id: ARCH-001\nversion: 1\nseverity: error\nmessage: 控制器不得直接依赖仓储层\n",
        encoding="utf-8",
        newline=chr(10),
    )
    stage2 = assert_clean(arm_dir)
    stages.append({"stage": "planted_path", "expect": "dirty", "observed": stage2["clean"], "detail": stage2})
    shutil.rmtree(tree / "policies", ignore_errors=True)

    note = tree / "notes.md"
    note.write_text("评审备注：这条改动大概率会命中 ARCH-001@1，先别提交。\n", encoding="utf-8", newline=chr(10))
    stage3 = assert_clean(arm_dir)
    stages.append({"stage": "planted_content", "expect": "dirty", "observed": stage3["clean"], "detail": stage3})
    note.unlink()

    stage4 = assert_clean(arm_dir)
    stages.append({"stage": "reverted", "expect": "clean", "observed": stage4["clean"], "detail": stage4})

    expected = [
        ("clean", True),
        ("planted_path", False),
        ("planted_content", False),
        ("reverted", True),
    ]
    verdicts = []
    for (name, want_clean), stage in zip(expected, stages):
        got_clean = bool(stage["observed"])
        verdicts.append(
            {
                "stage": name,
                "expected_clean": want_clean,
                "observed_clean": got_clean,
                "as_expected": got_clean is want_clean,
            }
        )
    ok = all(item["as_expected"] for item in verdicts)
    payload = {
        "ab_arm_schema_version": AB_ARM_SCHEMA_VERSION,
        "kind": "self-proof",
        "run_id": run_id,
        "run_dir": display(run_dir),
        "baseline": {"path": display(baseline), "digest": sha256_file(baseline)},
        "mutation": {
            "A_path": "往臂树里放回 policies/ARCH-001.yaml（路径删除层必须挡住）",
            "B_content": "往臂树里放 notes.md，正文含 ARCH-001@1（内容扫描层必须挡住）",
        },
        "stages": stages,
        "verdicts": verdicts,
        "instrument_goes_red": ok,
        "result": "pass" if ok else "fail",
        "note": (
            "这段证明的是**仪器会红**（AGENTS 第 45 条），不是'净化面已经完备'："
            "两个变异体各只覆盖一层防线，抓不到的复述形态照实写在 leak_scan.limits 里"
        ),
        "timestamp": reading.utc_now(),
    }
    write_json(run_dir / "self-proof.json", payload)
    return payload



def agent_version() -> str:
    """agent_version 只是配置字段；取不到就写 unknown，不编。"""

    path = REPO_ROOT / "adapters" / "dsh" / "manifest.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"^agent_version:\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def reading_context_payload(*, run_id: str, started_at: str, declarations: Mapping[str, Any]) -> Mapping[str, Any]:
    """读数属于哪棵树 / 哪个环境 / 哪套声明（唯一实现在 src/provenance/reading_context.py）。"""

    blocks = {
        reading.DECLARATION_REGISTRY: reading.declaration_block(
            REPO_ROOT / "validation" / "validators.yaml", root=REPO_ROOT
        ),
        reading.DECLARATION_TEST_LAYOUT: reading.declaration_block(
            REPO_ROOT / "validation" / "test-layout.yaml", root=REPO_ROOT
        ),
    }
    for name, value in declarations.items():
        blocks[str(name)] = dict(value)
    return reading.build(
        source=reading.SOURCE_CLI,
        tree=reading.tree_block(REPO_ROOT),
        declarations=blocks,
        host=reading.host_block(),
        run=reading.run_block(run_id=run_id, started_at=started_at),
    )


if __name__ == "__main__":
    raise SystemExit(main())
