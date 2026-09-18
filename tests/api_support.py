"""Phase 7 Policy API 的测试构造夹具：一份**隔离**的部署配置 + 租户边界。

为什么需要它（而不是在每个测试里手写 YAML）：

- 部署配置里的每个路径都是**边界**：规则目录、项目根、验证器配置、观测日志、索引库。
  用例必须能在互不干扰的临时目录里各建一份，否则"改了规则目录"的用例会污染别的用例；
- 相对路径的锚点是**仓库根优先、配置目录兜底**（见 policy_api.services.TenantStore._resolve）：
  因此配置里写的相对路径必须能相对**仓库根**解析；测试的临时目录在 `.tmp/tests/<hex>/...` 下，
  正好满足这一点，同时又不落在任何真实资源上；
- 令牌只以 sha256 出现（配置里出现明文会被 load_api_config 直接拒绝）：这里的明文常量
  只用于测试进程内构造 `Authorization` 头，绝不写进配置文件。

对外只暴露两件事：

- `write_api_config(...)`：把一份完整环境（项目、验证器配置、配置文件本身）写到临时目录，
  返回配置文件路径；
- `isolated_api(tmp_root, **kwargs)`：按惯例把路径算好（project / validation / corpus / db），
  返回 `(config_path, anchor)`，其中 anchor 就是仓库根——所有相对路径的解析基准。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from conftest import REPO_ROOT

from policy_api.config import hash_token

# --------------------------------------------------------------------------- 令牌

# 三个固定令牌：alpha 只被授权 alpha、both 被授权 alpha+beta、ops 带运维角色。
# 它们只存在于测试进程的内存里；配置文件里只有下面这串 sha256。
TOKEN = "alpha-secret-token"
TOKEN2 = "both-secret-token"
OPS_TOKEN = "ops-secret-token"
TOKEN_SHA = hash_token(TOKEN)
TOKEN2_SHA = hash_token(TOKEN2)
OPS_SHA = hash_token(OPS_TOKEN)

# --------------------------------------------------------------------------- 模板

# 部署配置模板（UTF-8 / LF）。`{}` 里是**相对仓库根**的路径或摘要，用 str.replace 生成：
# 这里刻意不用 str.format —— 模板里还有别的花括号时它会直接抛错或吃掉字段。
API_CONFIG_TEMPLATE = """schema_version: "1.0"
service_name: phase7-test
deployment: test
base_url: http://127.0.0.1:8088
limits:
  max_request_bytes: 65536
  max_response_bytes: 262144
  max_context_bytes: 32768
  max_prompt_chars: 8000
  max_concurrency: 4
budgets:
  evaluate_ms: 2000
  retrieve_ms: 4000
  validate_ms: 10000
rate_limit:
  capacity: 5
  refill_per_second: 0.001
audit:
  enabled: true
  path: {audit}
tenants:
  - tenant_id: alpha
    display_name: Alpha
    project: alpha-project
    project_root: {project}
    rules_root: {project}
    rules: [rules{rules_extra}]
    validation_root: {validation}
    audit_log: {tenant_audit}
{retrieval}  - tenant_id: beta
    display_name: Beta
    project: beta-project
    project_root: {project}
    rules_root: {project}
    rules: [rules]
    audit_log: {tenant_audit_beta}
{retrieval}clients:
  - client_id: alpha-client
    token_sha256: {token_sha}
    tenants: [alpha]
    projects: [alpha-project]
    roles: [developer]
  - client_id: both-client
    token_sha256: {token_sha2}
    tenants: [alpha, beta]
    projects: [alpha-project, beta-project]
    roles: [developer]
  - client_id: ops-client
    token_sha256: {ops_sha}
    tenants: [alpha, beta]
    roles: [ops]
metrics_clients: [ops-client]
"""

# 检索块：只有调用方给出 corpus_root + db 时才注入（不配置 = 该租户不提供检索能力，
# 这是显式状态，不是"检索降级成猜"）。两个租户共用同一份夹具索引：跨租户用例需要
# beta 也能走到 decision_ref 校验那一步，否则它会在"没有语料清单"处提前失败。
_RETRIEVAL_BLOCK = """    retrieval:
      enabled: true
      corpus: {corpus}
      database: {db}
"""

# 租户项目里的"好 controller"：只依赖 Service，ARCH-001（controller 不得直连 repository）
# 因此不应命中。夹具项目照抄 tests/fixtures/validators/project/src/shop/ 的样本。
_PROJECT_SOURCES: Mapping[str, str] = {
    "src/shop/__init__.py": '"""夹具项目的 shop 包。"""\n',
    "src/shop/order_controller.py": '''"""正例：Controller 只依赖 Service，ARCH-001 不应命中。"""

from shop.order_service import OrderService


class OrderController:
    """接口层：把请求转成服务调用。"""

    def __init__(self, service: OrderService) -> None:
        """注入业务用例层。"""

        self._service = service

    def create(self, payload: dict) -> dict:
        """处理创建请求。"""

        return self._service.create(payload)
''',
    "src/shop/order_service.py": '''"""业务用例层：只依赖数据访问层，不反向依赖接口层。"""

from shop.order_repository import OrderRepository


class OrderService:
    """订单用例。"""

    def __init__(self, repository: OrderRepository) -> None:
        """注入数据访问层。"""

        self._repository = repository

    def create(self, payload: dict) -> dict:
        """创建订单。"""

        return self._repository.save(payload)
''',
    "src/shop/order_repository.py": '''"""数据访问层：夹具里只保留结构，不连接任何真实存储。"""


class OrderRepository:
    """订单存储。"""

    def save(self, payload: dict) -> dict:
        """保存订单并回显。"""

        return dict(payload)
''',
}

# 模板里的占位符形态：替换完还剩下它们，说明 `str.replace` 漏了一条。
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")

# 验证器数据文件：注册表的默认路径是**相对 root 的** "validation/validators.yaml"
# （见 validators.registry.DEFAULT_REGISTRY / load_config），另外 tool.config 也是相对 root 的
# "validation/ruff.toml"，并在加载时逐个检查存在性（_check_registry）。因此租户的
# validation_root 是"包含 validation/ 的那个目录"（与仓库自己写的 validation_root: . 同义），
# 而不是 validation/ 本身；验证器流水线的临时目录写在 <validation_root>/.tmp/validators/<run>。
_TOOL_CONFIGS = ("ruff.toml", "mypy.ini", "pytest.ini")
_VALIDATION_FILES = ("validators.yaml", "project.yaml", "test-layout.yaml")


def _text_copy(source: Path, target: Path) -> Path:
    """文本复制：显式 UTF-8 + LF，避免平台换行把夹具的字节指纹改掉。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return target


def _relative_to_repo(path: Path) -> str:
    """把路径写成相对仓库根的 POSIX 形式（配置里的相对路径锚点就是仓库根）。

    落在仓库之外的路径按绝对路径原样给出：这时"锚点"没有意义，宁可写绝对路径，
    也不要让 `primary.exists()` 悄悄失败后再走"配置目录兜底"。
    """

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_project(project: Path, *, docs: bool) -> Path:
    """写出租户项目：规则目录 + 源码（+ 可选的 docs 目录）。"""

    project.mkdir(parents=True, exist_ok=True)
    _text_copy(
        REPO_ROOT / "policies" / "architecture" / "ARCH-001.yaml",
        project / "rules" / "ARCH-001.yaml",
    )
    for relative, text in _PROJECT_SOURCES.items():
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if docs:
        (project / "docs").mkdir(parents=True, exist_ok=True)
        (project / "docs" / "guide.md").write_text(
            "# 夹具文档\n\n这份文档只是为了让\"文档类路径\"的上下文有东西可指。\n",
            encoding="utf-8",
            newline="\n",
        )
    return project


def _copy_extra_rules(project: Path, sources: tuple[Path, ...]) -> tuple[Path, ...]:
    """把额外规则包**复制进租户项目**，返回项目内的绝对目录。

    为什么不直接指向仓库里的夹具目录：规则加载器会拒绝 rules_root 之外的规则文件
    （"规则文件 ... 不在规则目录 ... 之内，拒绝加载"），这是防止规则集被边界外文件污染的
    结构性约束。额外规则包因此必须像真实项目那样落在租户边界之内，配置里也就能继续用
    相对 rules_root 的语义（这里用绝对路径只是为了让两个锚点不同的解析规则都不出错）。
    """

    targets: list[Path] = []
    for source in sources:
        source = Path(source)
        target = project / "rules-extra" / source.name
        target.mkdir(parents=True, exist_ok=True)
        for item in sorted(source.glob("*.yaml")) + sorted(source.glob("*.yml")):
            _text_copy(item, target / item.name)
        targets.append(target)
    return tuple(targets)


def _write_validation(validation_root: Path) -> Path:
    """写出验证器配置：<root>/validation/ 下的注册表、项目档案、测试布局与工具配置。"""

    target = Path(validation_root) / "validation"
    target.mkdir(parents=True, exist_ok=True)
    source_root = REPO_ROOT / "validation"
    for name in (*_VALIDATION_FILES, *_TOOL_CONFIGS):
        _text_copy(source_root / name, target / name)
    return validation_root


def write_api_config(
    root: Path,
    *,
    project: Path,
    extra_rules: tuple[Path, ...] = (),
    docs: bool = False,
    validation_root: Path | None = None,
    corpus_root: Path | None = None,
    db: Path | None = None,
    token_hash: str = TOKEN_SHA,
    second_token_hash: str | None = None,
) -> Path:
    """在 root 下写一份完整的隔离环境，返回配置文件路径。

    参数即边界：

    - `project`：租户项目根（规则目录 `rules/` 与源码 `src/shop/` 写在里面）；
    - `extra_rules`：追加的规则目录（写成绝对路径，原因见下面的注释）；
    - `validation_root`：验证器配置根（**包含** `validation/` 的目录；None = 不写，
      alpha 就变成"没有验证器"的租户，validate 会以 validator_unavailable 失败关闭）；
    - `corpus_root` + `db`：检索语料根与索引库，两者必须一起给（只给一个说明调用方漏了边界）；
    - `docs`：是否给项目加一份 `docs/guide.md`（需要"文档路径"上下文的用例用）。
    """

    root = Path(root)
    project = _write_project(Path(project), docs=docs)
    if validation_root is not None:
        _write_validation(Path(validation_root))
    if (corpus_root is None) != (db is None):
        raise ValueError("corpus_root 与 db 必须同时给出：检索边界要么完整声明，要么不声明")

    audit_root = root / "audit"
    text = API_CONFIG_TEMPLATE
    # 先替换更长的占位符：{token_sha2} / {tenant_audit_beta} 以更短的占位符为前缀，
    # 顺序反了会把 "2" 与 "_beta" 留成字面量。
    text = text.replace("{token_sha2}", second_token_hash or TOKEN2_SHA)
    text = text.replace("{tenant_audit_beta}", _relative_to_repo(audit_root / "beta.jsonl"))
    text = text.replace("{tenant_audit}", _relative_to_repo(audit_root / "alpha.jsonl"))
    text = text.replace("{token_sha}", token_hash)
    text = text.replace("{ops_sha}", OPS_SHA)
    text = text.replace("{audit}", _relative_to_repo(audit_root / "service.jsonl"))
    text = text.replace("{project}", _relative_to_repo(project))
    text = text.replace(
        "{validation}",
        "null" if validation_root is None else _relative_to_repo(Path(validation_root)),
    )
    # 额外规则包：先复制进项目，再写成**绝对路径**。两个原因缺一不可：
    # 1) 规则加载器拒绝 rules_root 之外的规则文件（见 _copy_extra_rules）；
    # 2) TenantSpec.rules 的每一项都相对 `rules_root` 解析（TenantStore._assemble 里是
    #    `self._resolve(item, base=root)`），而 rules_root 是租户项目根、不是仓库根——
    #    写成"相对仓库根"会被解析成 `<project>/.tmp/tests/...`，租户直接装配失败。
    extra_dirs = _copy_extra_rules(project, extra_rules)
    rules_extra = "".join(f", {path.as_posix()}" for path in extra_dirs)
    text = text.replace("{rules_extra}", rules_extra)
    if corpus_root is not None and db is not None:
        block = _RETRIEVAL_BLOCK.replace(
            "{corpus}", _relative_to_repo(Path(corpus_root) / "knowledge" / "corpus.yaml")
        ).replace("{db}", _relative_to_repo(Path(db)))
        text = text.replace("{retrieval}", block)
    else:
        # 没有检索就不留占位符：空行是合法的 YAML，但"看得见的空占位符"会被误读成待填字段。
        text = text.replace("{retrieval}", "")
    leftover = _PLACEHOLDER_RE.findall(text)
    if leftover:  # 占位符没被替换掉 = 配置里会出现字面量 "{project}"，必须当场失败
        raise AssertionError(f"配置模板里还有未替换的占位符：{sorted(set(leftover))}")

    path = root / "api" / "policy-api.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def isolated_api(tmp_root: Path, **kwargs: Any) -> tuple[Path, Path]:
    """在 tmp_root 下装配一套隔离的 API：返回 `(配置文件路径, 锚点)`。

    锚点固定是仓库根：配置里的相对路径（项目、规则、验证器、语料、日志）都相对它解析，
    这与生产装配（`policy_api.testing.build_runtime(config, root=REPO_ROOT)`）完全一致。
    """

    root = Path(tmp_root)
    kwargs.setdefault("project", root / "project")
    # 验证器配置根的默认值就是 tmp_root 本身：注册表按 <root>/validation/*.yaml 读，
    # 流水线的临时目录按 <root>/.tmp/validators/<run> 写，两处都以它为锚。
    kwargs.setdefault("validation_root", root)
    config_path = write_api_config(root, **kwargs)
    return config_path, REPO_ROOT
