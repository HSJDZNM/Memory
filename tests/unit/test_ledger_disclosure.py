"""P6：台账"存什么"的自述必须与行为一致，而且这条口径要留在可评审文档里。

07 号报告 §4 P6 的现场：受控执行台账（`.policy/audit.enforcement-ledger.jsonl`）的
`pre_state` 记录里，`request.params[].value` 落的是**参数原文**、`request.workspace` 落的是
**绝对路径**；而 `src/enforcement/ledger.py` 的模块自述写着"台账只存标识、哈希与结论，
不存参数原文"，`src/enforcement/action.py::redacted_request_payload` 的 docstring 写着
"参数原文一律不落盘"。行为与自述对不上。

Lead 冻结的口径是**改自述、不改行为**，理由是三条互相独立的事实（下面"行为锁"逐条钉住）：

1. `src/adapters/dsh/enforcement.py::_restore_request` 要用台账里的 `request` 载荷
   **重建 `ActionRequest`**，这是 PostToolUse 事后核对的必要输入；
2. `src/enforcement/models.py::_ACTION_HASH_FIELDS` 里有 `workspace`，参数规范化取值也参与
   `compute_action_hash`；
3. 扣掉取值、或把 `workspace` 换成占位，重建必然对不上哈希 → 事后核对只能永远判"证据不足"
   → 等于把 G2（事前事后成对 + post_validated）打掉。

所以本文件有两半，缺一不可：

- **自述检查**（修复前会红）：两处 docstring 与术语文档里必须出现写死的口径字样，
  旧的那句绝对措辞必须消失；
- **行为锁**（修复前也绿，刻意如此）：非 secret 参数的 `value` 保留原文、`workspace` 保留
  绝对路径、请求视图能重建出同哈希的请求；secret 声明与确定形态凭据只留类型、长度与摘要。
  将来谁把行为改成"扣掉所有取值"，这一半会红——那时要改的是口径，不是测试。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from conftest import REPO_ROOT
from enforcement_support import EnforcementPaths, make_action, write_registry

from enforcement.action import redacted_request_payload
from enforcement.models import ActionRequest

LEDGER_SOURCE = REPO_ROOT / "src" / "enforcement" / "ledger.py"
ACTION_SOURCE = REPO_ROOT / "src" / "enforcement" / "action.py"
TERMINOLOGY_DOC = REPO_ROOT / "docs" / "project" / "architecture" / "术语与口径.md"

# 声明了 secret: true 的参数的默认注册表里没有（仓库真实注册表一个都没有），
# 所以这里造一个最小工具：一个 secret 参数 + 一个普通参数，用来看"逐个参数判"。
SECRET_TOOL = {
    "id": "probe.secret",
    "title": "test secret param",
    "agent": "dsh",
    "tool_name": "send_message",
    "schema_version": "1.0",
    "risk": "read_only",
    "effect": "none",
    "driver": "none",
    "required_permissions": ["repo.read"],
    "audit_failure": "degrade",
    "parameters": [
        {"name": "token", "type": "string", "required": True, "secret": True},
        {"name": "note", "type": "string", "required": True},
    ],
}


def _module_docstring(source: str) -> str:
    """取模块 docstring；没有就返回空串（删掉自述同样是一种不一致）。"""

    return ast.get_docstring(ast.parse(source)) or ""


def _function_docstring(source: str, name: str) -> str:
    """只取指定函数的 docstring：断言要落在自述那一段，而不是整个文件里碰巧出现的词。"""

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_docstring(node) or ""
    raise AssertionError(f"{name} 不存在：自述被删掉/改名同样是口径失守")


# --------------------------------------------------------------------------- 自述检查


def test_ledger_module_self_description_matches_what_is_written():
    """台账的自述必须逐项写清"存什么、扣什么、边界在哪"，而不是一句绝对措辞。"""

    doc = _module_docstring(LEDGER_SOURCE.read_text(encoding="utf-8"))

    # 旧的那句绝对措辞必须消失——它就是 P6 的现场
    assert "不存参数原文" not in doc
    # 存什么
    for token in ("kind", "action_hash", "请求视图"):
        assert token in doc, token
    # 扣什么：只有注册表 secret 声明与确定形态凭据
    assert "secret" in doc
    assert "values_withheld" in doc
    # 不扣什么：其余参数按原文落盘，workspace 落绝对路径且参与 action_hash
    assert "其余参数按原文落盘" in doc
    assert "绝对路径" in doc
    # 为什么：事后核对要拿这份载荷重建请求
    assert "重建" in doc and "_restore_request" in doc
    # 边界：这不是 AGENTS 第 16 条的违反，第 16 条管的是 audit.jsonl 摘要链
    assert "AGENTS" in doc and "16" in doc and "audit.jsonl" in doc


def test_request_view_docstring_states_the_same_rule():
    """`redacted_request_payload` 的自述与台账同一口径（函数名保留，含义写准）。"""

    doc = _function_docstring(ACTION_SOURCE.read_text(encoding="utf-8"), "redacted_request_payload")

    assert "参数原文一律不落盘" not in doc
    assert "其余参数按原文落盘" in doc
    assert "secret" in doc
    assert "values_withheld" in doc
    assert "绝对路径" in doc


def test_terminology_doc_freezes_the_ledger_disclosure():
    """口径要留在 .tmp 之外的可评审文档里：存什么 / 谁决定的 / 边界在哪。"""

    text = TERMINOLOGY_DOC.read_text(encoding="utf-8")

    assert "按原文落盘" in text
    assert "绝对路径" in text
    assert "values_withheld" in text
    assert "_restore_request" in text
    # 谁决定的：本轮冻结的依据是 07 号报告的 P6
    assert "P6" in text
    # 边界：与 AGENTS 第 16 条（audit.jsonl 摘要链）不是同一条
    assert "AGENTS" in text and "第 16 条" in text and "audit.jsonl" in text


# --------------------------------------------------------------------------- 行为锁（修复前也绿）


def test_plain_params_keep_their_text_and_workspace_stays_absolute(tmp_root):
    """非 secret 参数按原文落盘、workspace 落绝对路径；这份视图必须能重建出同哈希的请求。"""

    paths = EnforcementPaths(tmp_root / "ledger-plain")
    registry = paths.registry_object()
    content = "VALUE = 1" + chr(10) + "# 中文注释也要能重建" + chr(10)

    request = make_action(
        registry, paths, "fs.write", {"file_path": "src/plain.py", "content": content}
    )
    payload = redacted_request_payload(request)

    assert payload["values_withheld"] is False
    content_value = next(item for item in payload["params"] if item["name"] == "content")
    assert content_value["value"] == content
    assert content_value["chars"] == len(content)
    assert content_value["digest"].startswith("sha256:")

    # workspace 落的是绝对路径：它不是"顺手多写的字段"，而是 action_hash 的参与字段
    assert payload["workspace"] == paths.workspace.as_posix()
    assert Path(payload["workspace"]).is_absolute()

    # 生产路径同款重建：_restore_request 就是对这个载荷做 model_validate
    stored = {key: value for key, value in payload.items() if key != "values_withheld"}
    rebuilt = ActionRequest.model_validate(stored)
    assert rebuilt.action_hash == request.action_hash
    assert rebuilt.workspace == request.workspace
    assert rebuilt.value_of("content") == content


def test_declared_secret_is_withheld_while_siblings_are_not(tmp_root):
    """注册表声明 secret 的参数只留类型/长度/摘要；同一次请求里的普通参数照旧落原文。"""

    paths = EnforcementPaths(tmp_root / "ledger-secret")
    write_registry(paths.root, tools=(SECRET_TOOL,))
    registry = paths.registry_object()

    request = make_action(
        registry, paths, "probe.secret", {"token": "hunter2", "note": "普通文本"}
    )
    payload = redacted_request_payload(request)

    assert payload["values_withheld"] is True
    secret_param = next(item for item in payload["params"] if item["name"] == "token")
    note_param = next(item for item in payload["params"] if item["name"] == "note")
    assert secret_param["secret"] is True
    assert secret_param["value"] is None
    assert secret_param["chars"] == len("hunter2")
    assert secret_param["digest"].startswith("sha256:")
    # 扣留是**逐个参数**判的：声明 secret 不牵连同一次请求里的普通参数
    assert note_param["value"] == "普通文本"


def test_credential_shaped_value_is_withheld_by_shape(tmp_root):
    """取值里出现确定形态凭据时同样扣留：这是"像密钥的值"这一半的判据。"""

    paths = EnforcementPaths(tmp_root / "ledger-credential")
    registry = paths.registry_object()
    token = "ghp_" + "abcdefghijklmnopqrst"  # secret-scan: allow（合成值，验证扣留逻辑）

    request = make_action(
        registry,
        paths,
        "fs.write",
        {"file_path": "src/config.py", "content": 'TOKEN = "' + token + '"' + chr(10)},
    )
    payload = redacted_request_payload(request)

    assert payload["values_withheld"] is True
    content_value = next(item for item in payload["params"] if item["name"] == "content")
    assert content_value["value"] is None
    # 摘要仍在：结论可核验，只是无法重建原文（PostToolUse 据此判"证据不足"）
    assert content_value["digest"] in json.dumps(payload, ensure_ascii=False)
    stored = json.dumps(
        {key: value for key, value in payload.items() if key != "values_withheld"},
        ensure_ascii=False,
    )
    assert token not in stored
