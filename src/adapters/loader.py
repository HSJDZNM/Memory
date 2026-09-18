"""Adapter 装配：把 manifest（能力声明）与 adapter 配置装成可用的 Adapter。

装配是**原子**的：manifest 的哈希必须与 `adapters/approved.json` 一致，
配置必须存在且合法，工作区必须真的存在——任何一项不满足都拒绝装配。
"改一份 YAML 就给自己加上完整 enforcement" 这条路径必须被审核挡住。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import yaml
from pydantic import ValidationError

from policy.models import RuleValidationError

from .base import (
    DEFAULT_ADAPTERS_ROOT,
    DEFAULT_APPROVED_PATH,
    Adapter,
    AdapterConfig,
    AdapterRegistry,
    RegistryError,
)
from .event_adapter import EventAdapter
from .json_adapter import JsonAdapter
from .models import AdapterManifest, AgentEvent, EnforcementLevel, ManifestError

__all__ = [
    "ADAPTER_FACTORIES",
    "build_adapter",
    "load_adapter",
    "load_adapters",
    "load_registry_from_repo",
    "repo_root",
]

def _dsh_adapter() -> type[Adapter]:
    """延迟导入：dsh 的实现只在真正用到它时才加载。"""

    from .dsh_adapter import DshAdapter

    return DshAdapter


# 契约（manifest 里的 protocol）→ 实现类。新增一种 Agent 时只在这里登记一次，
# 核心层与一致性套件都不需要改。
ADAPTER_FACTORIES: Mapping[str, Callable[[], type[Adapter]]] = {
    "canonical-json": lambda: JsonAdapter,
    "hook-command": lambda: EventAdapter,
    # dsh 的工具表同时存在于代码（Phase 2 的 TOOL_TABLE，受契约测试保护）与
    # manifest（能力声明）。两条来源必须一致，见 tests/contract/test_agent_adapters.py。
    "canonical-tool-table": _dsh_adapter,
}


def repo_root(
    start: Optional[Path | str] = None,
) -> Path:
    """仓库根目录：向上回溯到**真的装着能力声明**的那一层。

    只看"有没有 adapters 目录"是不够的：这个模块自己就住在 src/adapters 里，
    于是 src/ 会被误判成仓库根。判据因此收紧成
    "adapters/ 下有 manifest.yaml，或这一层有 pyproject.toml / .git"。
    """

    here = (Path(start) if start is not None else Path(__file__).resolve()).resolve()
    for candidate in (here, *here.parents):
        root = candidate / DEFAULT_ADAPTERS_ROOT
        if root.is_dir() and any(root.glob("*/manifest.yaml")):
            return candidate
        if (candidate / "pyproject.toml").is_file() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def load_registry_from_repo(
    root: Optional[Path | str] = None,
    *,
    require_approval: bool = True,
) -> AdapterRegistry:
    base = Path(root) if root is not None else repo_root()
    return AdapterRegistry.load(
        base / DEFAULT_ADAPTERS_ROOT,
        approved_path=base / DEFAULT_APPROVED_PATH,
        require_approval=require_approval,
    )


def load_adapter_config(path: Path | str) -> AdapterConfig:
    target = Path(path)
    if not target.is_file():
        raise RegistryError(f"adapter 配置不存在：{target}")
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise RegistryError(f"{target}: 配置不可读 ({error})") from error
    if not isinstance(document, Mapping):
        raise RegistryError(f"{target}: 顶层必须是映射，得到 {type(document).__name__}")
    try:
        return AdapterConfig.model_validate(dict(document))
    except ValidationError as error:
        failure = RuleValidationError.from_pydantic(error, model_name=f"adapter 配置 {target}")
        raise RegistryError(str(failure)) from error


def build_adapter(
    *,
    manifest: AdapterManifest,
    config: AdapterConfig,
    config_path: Path | str,
    base_dir: Optional[Path] = None,
) -> Adapter:
    """按 manifest 声明的协议选实现类；没登记过的协议显式失败。"""

    from .models import EnforcementLevel

    protocol = manifest.protocol.strip()
    factory = ADAPTER_FACTORIES.get(protocol)
    if factory is None:
        known = sorted(ADAPTER_FACTORIES)
        raise RegistryError(
            f"未知 adapter 协议 {protocol!r}（agent={manifest.agent_id}）："
            f"已登记 {known}；新增协议必须先实现适配器并在 ADAPTER_FACTORIES 登记，"
            "不能在运行时按名字猜"
        )
    return factory()(
        manifest=manifest,
        config=config,
        config_path=config_path,
        base_dir=base_dir,
    )


def load_adapter(
    agent_id: str,
    *,
    root: Optional[Path | str] = None,
    config_path: Optional[Path | str] = None,
    registry: Optional[AdapterRegistry] = None,
) -> Adapter:
    """装配单个 Adapter：`adapters/<agent_id>/manifest.yaml` + `adapter.yaml`。"""

    base = Path(root) if root is not None else repo_root()
    loaded = registry if registry is not None else load_registry_from_repo(base)
    manifest = loaded.manifest(agent_id)
    descriptor = loaded.as_list().get(agent_id)
    if not descriptor.approved:
        raise RegistryError(
            f"Agent {agent_id!r} 的能力声明尚未审核或已漂移："
            "改声明必须重新审核（python -m adapters.cli approve --reviewer <name>）；"
            "未审核的 Adapter 不得接入"
        )
    if descriptor.enforcement is EnforcementLevel.UNSUPPORTED:
        raise RegistryError(
            f"Agent {agent_id!r} 当前不可接入（能力不足）："
            + "；".join(descriptor.ceiling_reasons)
            + "。不得把它当成可治理的 Agent 接入"
        )
    target = (
        Path(config_path)
        if config_path is not None
        else base / DEFAULT_ADAPTERS_ROOT / agent_id / "adapter.yaml"
    )
    config = load_adapter_config(target)
    return build_adapter(
        manifest=manifest,
        config=config,
        config_path=target.name,
        base_dir=target.parent,
    )


def load_adapters(
    agent_ids: Sequence[str],
    *,
    root: Optional[Path | str] = None,
    configs: Optional[Mapping[str, Path | str]] = None,
    registry: Optional[AdapterRegistry] = None,
) -> dict[str, Adapter]:
    base = Path(root) if root is not None else repo_root()
    loaded = registry if registry is not None else load_registry_from_repo(base)
    result: dict[str, Adapter] = {}
    for agent_id in agent_ids:
        override = None if configs is None else configs.get(agent_id)
        result[agent_id] = load_adapter(
            agent_id, root=base, config_path=override, registry=loaded
        )
    return result
