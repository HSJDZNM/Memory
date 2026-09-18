"""测试共享工具：路径注入、定位仓库根目录、构造上下文与规则。"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

# Phase 5 的夹具项目是**被验证的样本**，它的 tests/ 必须能被测试验证器真的收集到，
# 因此只能在仓库自己的收集路径上屏蔽它（而不是在夹具项目里加 collect_ignore）。
collect_ignore_glob = ["fixtures/validators/project/tests/*"]
TOOLS_DIR = REPO_ROOT / "tools"
TMP_ROOT = REPO_ROOT / ".tmp" / "tests"

# 允许在未安装项目时直接运行测试（uv sync 之后这一行只是幂等的保险）。
# tools/ 也加进来：性能基线生成器（tools/policy_bench.py）由测试与阶段证据共用同一份实现。
for directory in (SRC_DIR, TOOLS_DIR):
    if directory.is_dir() and str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from policy.loader import load_rule_set  # noqa: E402
from policy.models import PolicyContext, Rule, RuleSet  # noqa: E402

__all__ = [
    "ARCH_DIR",
    "DSH_EVENT_FIXTURES",
    "DSH_LANGUAGES",
    "DSH_LAYERS",
    "FAKE_TOOL",
    "FIXTURES_DIR",
    "POLICIES_DIR",
    "REPO_ROOT",
    "RETRIEVAL_DATASETS",
    "RETRIEVAL_FIXTURES",
    "RETRIEVAL_POLICY",
    "RULE_DOCUMENT",
    "VALIDATION_DIR",
    "VALIDATOR_FIXTURES",
    "VALIDATOR_PROJECT",
    "copy_validator_project",
    "dsh_event",
    "fake_tool_spec",
    "make_checker_rule",
    "validators_config",
    "write_validation_config",
    "fixture_file_sha256",
    "module_tmp_root",
    "tmp_root_factory",
    "load_fixture_corpus",
    "write_fixture_corpus",
    "make_context",
    "make_rule",
    "rule_document",
    "write_dsh_config",
    "write_rule",
]

POLICIES_DIR = REPO_ROOT / "policies"
ARCH_DIR = POLICIES_DIR / "architecture"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
DSH_EVENT_FIXTURES = FIXTURES_DIR / "agent_events" / "dsh"

# dsh Adapter 的显式上下文来源：layer 与 language 只由声明决定，绝不从文件名推断。
DSH_LAYERS: tuple[tuple[str, str], ...] = (
    ("**/*_controller.py", "controller"),
    ("**/*_service.py", "service"),
    ("**/*_repository.py", "repository"),
)
DSH_LANGUAGES: tuple[tuple[str, str], ...] = (("**/*.py", "python"),)


def dsh_event(name: str, **overrides: Any) -> dict[str, Any]:
    """读取脱敏的 dsh 事件 fixture；覆盖字段时只改本次测试关心的那一项。"""

    payload = json.loads((DSH_EVENT_FIXTURES / name).read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def write_dsh_config(
    path: Path,
    *,
    project_root: Path,
    rules: Path,
    **overrides: Any,
) -> Path:
    """写一份 dsh adapter 配置（YAML），默认声明 layer/language 与 5s 内部预算。"""

    document: dict[str, Any] = {
        "agent_version": "0.1.5-rc.1",
        "project": "demo-shop",
        "project_root": str(project_root),
        "rules": [str(rules)],
        "rules_root": str(REPO_ROOT),
        "timeout_ms": 5000,
        "layers": [{"pattern": pattern, "layer": layer} for pattern, layer in DSH_LAYERS],
        "languages": [
            {"pattern": pattern, "language": language} for pattern, language in DSH_LANGUAGES
        ],
        "audit_log": str(path.parent / "audit.jsonl"),
        # Phase 4：受控工具需要显式主体与工具注册表；缺任一项都由 Hook 失败关闭。
        "principal": {"subject": "local-user", "roles": ["developer"]},
        "registry": str(REPO_ROOT / "registry" / "tool-registry.yaml"),
        "registry_approved": str(REPO_ROOT / "registry" / "tool-registry.approved.json"),
    }
    document.update(overrides)
    for key in [key for key, value in document.items() if value is None]:
        if key in overrides:
            document.pop(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


@pytest.fixture()
def dsh_project(tmp_root: Path) -> Path:
    """受控 dsh 项目根：只需要目录结构（Adapter 不读文件内容，只规范化路径）。"""

    root = tmp_root / "demo-shop"
    (root / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def dsh_config_path(tmp_root: Path, dsh_project: Path) -> Path:
    """默认的 adapter 配置（规则目录指向仓库真实 policies/）。"""

    return write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=dsh_project,
        rules=POLICIES_DIR,
    )

RULE_DOCUMENT: dict[str, Any] = {
    "id": "ARCH-001",
    "version": 1,
    "name": "controller-service-boundary",
    "description": "Controller 不得直接访问 Repository。",
    "scope": {"language": "python", "layer": "controller"},
    "severity": "error",
    "enforcement": {"type": "deterministic", "checker": "forbidden_dependency"},
    "rule": {"forbidden_dependency": ["repository"]},
    "message": "Controller 必须通过 Service 访问 Repository。",
    "source": {"kind": "project-policy", "path": "policies/architecture/ARCH-001.yaml"},
}


def rule_document(**overrides: Any) -> dict[str, Any]:
    """返回 RULE_DOCUMENT 的深拷贝；传 None 表示删除该字段。"""

    document = copy.deepcopy(RULE_DOCUMENT)
    for key, value in overrides.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    return document


@pytest.fixture()
def arch_rule() -> Rule:
    """ARCH-001@1，来自仓库真实规则文件。"""

    rules = load_rule_set([ARCH_DIR], repo_root=REPO_ROOT)
    assert len(rules) == 1
    return rules.rules[0]


@pytest.fixture()
def arch_rules(arch_rule: Rule) -> RuleSet:
    return RuleSet(rules=(arch_rule,), source_paths=("policies/architecture/ARCH-001.yaml",))


def make_rule(
    rule_id: str = "ARCH-001",
    *,
    version: int = 1,
    scope: dict[str, Any] | None = None,
    severity: str = "error",
    forbidden: tuple[str, ...] = ("repository",),
    checker: str = "forbidden_dependency",
    requires_approval: bool = False,
    message: str = "Controller 必须通过 Service 访问 Repository。",
) -> Rule:
    """按 RULE_DOCUMENT 原型构造一条规则，只覆盖本次测试关心的字段。"""

    return Rule.model_validate(
        rule_document(
            id=rule_id,
            version=version,
            scope={"language": "python", "layer": "controller"} if scope is None else scope,
            severity=severity,
            enforcement={
                "type": "deterministic",
                "checker": checker,
                "requires_approval": requires_approval,
            },
            rule={"forbidden_dependency": list(forbidden)},
            message=message,
        )
    )


def make_context(**overrides: Any) -> PolicyContext:
    payload: dict[str, Any] = {
        "request_id": "req-123",
        "file": "src/order/controller.py",
        "language": "python",
        "layer": "controller",
        "dependencies": [],
    }
    payload.update(overrides)
    return PolicyContext(**payload)


def write_rule(path: Path, document: dict[str, Any], *, yaml_module: Any) -> Path:
    """把规则文档写成 YAML 文件，返回路径。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml_module.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="module")
def module_tmp_root() -> Any:
    """模块级临时目录（同样只用 mkdir，不依赖 mkdtemp/chmod）。

    一致性套件这类"跑一次、多个用例共用结论"的夹具需要模块级作用域，
    而 tmp_root 是函数级的；两者的实现必须一致，否则沙箱里会出现
    "有的用例能跑、有的用例因为权限失败"这种与被测行为无关的差异。
    """

    directory = TMP_ROOT / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture()
def tmp_root_factory() -> Any:
    """按需创建多个独立临时目录（模块级 fixture 需要它）。

    与 tmp_root 同一套实现：只用 mkdir + 唯一名字，不依赖 mkdtemp/chmod——
    受限沙箱里那两个调用会被拒绝，从而制造与被测行为无关的失败。
    """

    created: list[Path] = []

    def make() -> Path:
        directory = TMP_ROOT / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=True)
        created.append(directory)
        return directory

    try:
        yield make
    finally:
        for directory in created:
            shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture()
def tmp_root() -> Any:
    """提供一个独立的临时目录，测试结束后清理。

    刻意不用 pytest 的 tmp_path：它依赖 tempfile.mkdtemp，而在受限沙箱里 chmod/mkdtemp
    会被拒绝，导致与规则加载本身无关的权限错误。本 fixture 只用 mkdir + 唯一名字，
    因此在普通开发机和沙箱里行为一致。
    """

    directory = TMP_ROOT / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------- Phase 3

RETRIEVAL_FIXTURES = FIXTURES_DIR / "retrieval_corpus"

# 夹具目录 → 数据集定义。第一段目录名就是镜像目录名，其余部分是镜像内 local_path。
RETRIEVAL_DATASETS: tuple[dict[str, Any], ...] = (
    {
        "name": "guides",
        "title": "Fixture Guides",
        "mirror": "mirror/guides",
        "license": "CC0-1.0 (fixture)",
        "tier": "guidance",
        "visibility": "public",
        "files": ("guides/index.md", "guides/topics.md"),
    },
    {
        "name": "restricted-docs",
        "title": "Fixture Restricted Docs",
        "mirror": "mirror/restricted",
        "license": "CC0-1.0 (fixture)",
        "tier": "guidance",
        "visibility": "restricted",
        "files": ("restricted/internal.md",),
    },
    {
        "name": "adversarial",
        "title": "Fixture Adversarial Corpus",
        "mirror": "mirror/adversarial",
        "license": "CC0-1.0 (fixture)",
        "tier": "reference",
        "visibility": "public",
        "files": ("adversarial/poisoned.md",),
    },
)

RETRIEVAL_POLICY: dict[str, Any] = {
    "top_k": 5,
    "max_query_chars": 200,
    "max_query_terms": 24,
    "max_chunk_chars": 400,
    "hard_max_chunk_chars": 1200,
    "context_budget_chars": 1500,
    "max_snippet_chars": 600,
    "max_snippets": 5,
    "expansion": None,
}


def fixture_file_sha256(path: Path) -> str:
    """夹具文件的 sha256（带 sha256: 前缀），与索引库里的哈希口径一致。"""

    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture_corpus(
    root: Path,
    *,
    policy: dict[str, Any] | None = None,
    quarantine: list[dict[str, Any]] | None = None,
    rule_sources: list[dict[str, Any]] | None = None,
    drift: tuple[str, ...] = (),
    drop_files: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
) -> Path:
    """在临时目录里生成"镜像 + manifest.json + 摄取清单"，返回 corpus.yaml 路径。

    manifest.json 的 sha256 由运行时计算，因此夹具内容改动不会造成假漂移；
    需要测漂移时用 drift 指定条目（写入一个错误的哈希）。
    """

    datasets: list[dict[str, Any]] = []
    for spec in RETRIEVAL_DATASETS:
        mirror_root = root / spec["mirror"]
        mirror_root.mkdir(parents=True, exist_ok=True)
        pages: list[dict[str, Any]] = []
        entries: list[str] = []
        for relative in spec["files"]:
            if relative in drop_files:
                continue
            source = RETRIEVAL_FIXTURES / relative
            local_path = "/".join(Path(relative).parts[1:])
            target = mirror_root / local_path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = (overrides or {}).get(relative, source.read_text(encoding="utf-8"))
            target.write_text(content, encoding="utf-8", newline="")
            digest = fixture_file_sha256(target)
            if relative in drift:
                digest = "sha256:" + "0" * 64
            pages.append(
                {
                    "local_path": local_path,
                    "source_url": f"https://example.invalid/{relative}",
                    "title": Path(local_path).stem.replace("-", " ").title(),
                    "sha256": digest,
                    "bytes": target.stat().st_size,
                    "saved": True,
                    "status": 200,
                }
            )
            entries.append(local_path)
        (mirror_root / "manifest.json").write_text(
            json.dumps(
                {
                    "source": "https://example.invalid/",
                    "fetched_at": "2026-09-16T00:00:00Z",
                    "pages": pages,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="",
        )
        datasets.append(
            {
                "name": spec["name"],
                "title": spec["title"],
                "mirror": spec["mirror"],
                "license": spec["license"],
                "tier": spec["tier"],
                "visibility": spec["visibility"],
                "entries": entries,
            }
        )

    document: dict[str, Any] = {
        "version": 1,
        "policy": {**RETRIEVAL_POLICY, **(policy or {})},
        "datasets": datasets,
        "restricted_datasets": ["restricted-docs"],
        "quarantine": list(quarantine or []),
        "rule_sources": list(rule_sources or []),
    }
    path = root / "knowledge" / "corpus.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8", newline=""
    )
    return path


def load_fixture_corpus(root: Path, **overrides: Any) -> Any:
    """写夹具语料并加载成 LoadedCorpus。"""

    from retrieval.corpus import load_corpus

    path = write_fixture_corpus(root, **overrides)
    return load_corpus(path, repo_root=root)


@pytest.fixture()
def retrieval_corpus(tmp_root: Path) -> Any:
    return load_fixture_corpus(tmp_root)


@pytest.fixture()
def retrieval_store(tmp_root: Path) -> Any:
    from retrieval.store import ChunkStore

    store = ChunkStore(tmp_root / "index.sqlite3")
    try:
        yield store
    finally:
        store.close()


# --------------------------------------------------------------------------- Phase 5

VALIDATOR_FIXTURES = FIXTURES_DIR / "validators"
VALIDATOR_PROJECT = VALIDATOR_FIXTURES / "project"
FAKE_TOOL = VALIDATOR_FIXTURES / "tools" / "fake_tool.py"

VALIDATION_DIR = REPO_ROOT / "validation"


def validators_config(
    *,
    root: Path = REPO_ROOT,
    registry: Path | None = None,
    project: Path | None = None,
    test_layout: Path | None = None,
) -> Any:
    """加载验证器配置；默认用仓库真实的三份数据文件。"""

    from validators.registry import load_config

    return load_config(root=root, registry=registry, project=project, test_layout=test_layout)


def write_validation_config(
    root: Path,
    *,
    registry: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    test_layout: dict[str, Any] | None = None,
) -> Path:
    """在临时目录写一份 validation/ 配置（默认复制仓库真实数据），返回配置根目录。

    tool.config 之类的仓库内路径仍以仓库根为锚：测试里通过 registry 传相对路径，
    由调用方决定用哪个 root 加载。
    """

    target = root / "validation"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "validators.yaml",
        "project.yaml",
        "test-layout.yaml",
        "ruff.toml",
        "mypy.ini",
        "pytest.ini",
    ):
        (target / name).write_text(
            (VALIDATION_DIR / name).read_text(encoding="utf-8"), encoding="utf-8", newline=""
        )
    for name, document in (
        ("validators.yaml", registry),
        ("project.yaml", project),
        ("test-layout.yaml", test_layout),
    ):
        if document is not None:
            (target / name).write_text(
                yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
                newline="",
            )
    return root


def make_checker_rule(
    rule_id: str = "DOC-001",
    *,
    checker: str = "missing_docstring",
    body: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
    severity: str = "error",
    version: int = 1,
) -> Any:
    """按 checker 构造一条规则（Phase 5 的规则体是 per-checker 的）。"""

    bodies: dict[str, dict[str, Any]] = {
        "forbidden_dependency": {"forbidden_dependency": ["repository"]},
        "missing_docstring": {"missing_docstring": {"targets": ["module", "class", "function"]}},
        "style_lint": {"style_lint": {"tool": "ruff", "codes": ["E501"]}},
        "type_check": {"type_check": {"tool": "mypy", "codes": []}},
        "missing_tests": {"missing_tests": {"changed_only": True}},
        "failing_tests": {"failing_tests": {"tool": "pytest"}},
    }
    document = rule_document(
        id=rule_id,
        version=version,
        scope={"language": "python"} if scope is None else scope,
        severity=severity,
        enforcement={"type": "deterministic", "checker": checker},
        rule=bodies[checker] if body is None else body,
    )
    from policy.models import Rule

    return Rule.model_validate(document)


def fake_tool_spec(
    tool: str = "ruff",
    behaviour: str = "ok",
    *,
    validator_id: str | None = None,
    checkers: tuple[str, ...] = ("style_lint",),
    argv: tuple[str, ...] = ("check", "--output-format=json", "{paths}"),
    version_requirement: str | None = None,
    stage: str = "lint",
    critical: bool = True,
    timeout_ms: int | None = None,
) -> Any:
    """构造一个指向假工具的外部验证器声明（失效与边界测试用）。"""

    from policy.evidence import ValidatorKind
    from validators.models import ToolSpec, ValidatorSpec

    requirements = {"ruff": ">=0.6,<1", "mypy": ">=1.8,<2", "pytest": ">=8"}
    return ValidatorSpec(
        id=validator_id or ("tool." + tool),
        version="1.0",
        kind=ValidatorKind.EXTERNAL,
        stage=stage,
        checkers=checkers,
        critical=critical,
        timeout_ms=timeout_ms,
        tool=ToolSpec(
            command=(sys.executable, str(FAKE_TOOL), tool, behaviour),
            version_args=("--version",),
            version_pattern=tool + r" (\d+\.\d+[0-9A-Za-z.\-+]*)",
            version_requirement=(
                requirements[tool] if version_requirement is None else version_requirement
            ),
            argv=argv,
        ),
    )


def copy_validator_project(tmp_root: Path, *, name: str = "project") -> Path:
    """把夹具项目复制到临时目录（需要改动工作区的用例用它）。"""

    target = tmp_root / name
    shutil.copytree(VALIDATOR_PROJECT, target)
    return target


@pytest.fixture()
def validator_project() -> Path:
    """夹具项目根目录（只读使用；需要改动时用 copy_validator_project）。"""

    return VALIDATOR_PROJECT
