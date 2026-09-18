"""policy_api.cli：部署与运维的命令行入口。

    python -m policy_api.cli serve                    # 启动 ASGI 服务（装配失败即拒绝启动）
    python -m policy_api.cli self-check               # 配置 / 租户 / readiness / 契约 自检
    python -m policy_api.cli openapi --check          # OpenAPI 快照是否漂移（CI 门禁）
    python -m policy_api.cli openapi --write          # 显式更新快照（需要评审）
    python -m policy_api.cli clients                  # 列出客户端（只显示摘要，不显示令牌）
    python -m policy_api.cli clients --hash           # 从 stdin 读一个令牌并输出 sha256
    python -m policy_api.cli smoke --token <token>    # 进程内跑一遍最小链路（不开端口）
    python -m policy_api.cli seal --out anchor.json   # 把观测日志的链末值封成对外锚定文件
    python -m policy_api.cli seal --verify anchor.json  # 校验日志是否被删尾/改写

退出码：0 通过；1 契约/自检不通过；2 配置或用法错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .config import ApiConfig, ConfigError, hash_token, load_api_config
from .errors import ApiError
from .models import API_SCHEMA_VERSION
from .runtime import ApiRuntime

__all__ = [
    "EXIT_ERROR",
    "EXIT_OK",
    "EXIT_UNHEALTHY",
    "build_parser",
    "default_config_path",
    "main",
    "run",
]

EXIT_OK = 0
EXIT_UNHEALTHY = 1
EXIT_ERROR = 2

DEFAULT_CONFIG = Path("api") / "policy-api.yaml"
SNAPSHOT = Path("api") / "openapi.json"


def default_config_path(root: Path) -> Path:
    return root / DEFAULT_CONFIG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m policy_api.cli",
        description="Policy API 的部署、契约与运维入口（Phase 7）。",
    )
    parser.add_argument(
        "command",
        choices=("serve", "self-check", "openapi", "clients", "smoke", "seal"),
        help="serve=启动服务；self-check=装配与 readiness；openapi=契约快照；"
        "clients=客户端清单；smoke=进程内最小链路；seal=观测日志对外锚定/校验",
    )
    parser.add_argument("--config", default=None, help="部署配置路径（默认 api/policy-api.yaml）")
    parser.add_argument("--root", default=None, help="路径解析锚点（默认仓库根）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--check", action="store_true", help="openapi：只比较快照，不写文件")
    parser.add_argument("--write", action="store_true", help="openapi：显式重写快照")
    parser.add_argument("--hash", action="store_true", help="clients：从 stdin 读令牌并输出 sha256")
    parser.add_argument("--token", default=None, help="smoke：使用的令牌（默认取配置里第一个客户端）")
    parser.add_argument("--out", default=None, help="seal：锚定文件写到哪里")
    parser.add_argument("--verify", default=None, help="seal：校验哪个锚定文件")
    parser.add_argument("--log-level", default="info", help="serve：uvicorn 日志级别")
    return parser


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "policies").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _resolve(args: argparse.Namespace) -> tuple[Path, Path]:
    root = Path(args.root).resolve() if args.root else repo_root()
    config_path = Path(args.config) if args.config else default_config_path(root)
    if not config_path.is_absolute():
        config_path = root / config_path
    return root, config_path


def _load(args: argparse.Namespace) -> tuple[Path, Path, ApiConfig]:
    root, path = _resolve(args)
    config = load_api_config(path, root=root)
    return root, path, config


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root, path, config = _load(args)
    except ConfigError as error:
        print(f"policy-api: 配置不可用：{error}", file=sys.stderr)
        return EXIT_ERROR

    if args.command == "serve":
        from .serve import serve

        return serve(path, root=root, log_level=args.log_level)

    if args.command == "clients":
        return _clients(args, config)

    if args.command == "openapi":
        return _openapi(args, config, root)

    if args.command == "smoke":
        return _smoke(args, config, root)

    if args.command == "seal":
        return _seal(args, config, root)

    return _self_check(args, config, root)


def _clients(args: argparse.Namespace, config: ApiConfig) -> int:
    if args.hash:
        token = sys.stdin.readline().strip()
        if not token:
            print("policy-api: 需要从 stdin 读到一个非空令牌", file=sys.stderr)
            return EXIT_ERROR
        digest = hash_token(token)
        if args.json:
            print(json.dumps({"token_sha256": digest}, ensure_ascii=False))
        else:
            print(digest)
        return EXIT_OK
    rows = [
        {
            "client_id": client.client_id,
            "tenants": list(client.tenants),
            "projects": list(client.projects),
            "roles": list(client.roles),
            "token_ref": client.token_sha256[:12],
            "enabled": client.enabled,
            "expires_at": client.expires_at,
        }
        for client in config.clients
    ]
    if args.json:
        print(json.dumps({"clients": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(
                f"{row['client_id']:<20} tenants={','.join(row['tenants']):<24} "
                f"roles={','.join(row['roles']) or '-':<16} token={row['token_ref']} "
                f"enabled={row['enabled']}"
            )
    return EXIT_OK


def _openapi(args: argparse.Namespace, config: ApiConfig, root: Path) -> int:
    from .contract import openapi_document, snapshot_diff, write_snapshot

    runtime = ApiRuntime(config, root=root)
    document = openapi_document(runtime)
    target = root / SNAPSHOT
    if args.write:
        write_snapshot(target, document)
        print(f"policy-api: OpenAPI 快照已更新 -> {SNAPSHOT.as_posix()}")
        return EXIT_OK
    issues = snapshot_diff(target, document)
    if issues:
        print("[openapi] %d 处漂移：" % len(issues))
        for item in issues:
            print("  ! " + item)
        print("契约变化必须显式评审：确认后运行 python -m policy_api.cli openapi --write")
        return EXIT_UNHEALTHY
    print("[openapi] 与快照一致（api_version=%s）" % API_SCHEMA_VERSION)
    return EXIT_OK


def _smoke(args: argparse.Namespace, config: ApiConfig, root: Path) -> int:
    from .contract import smoke

    token = args.token
    if token is None:
        if not config.clients:
            print("policy-api: 配置里没有客户端，无法冒烟", file=sys.stderr)
            return EXIT_ERROR
        print(
            "policy-api: 未提供 --token；smoke 需要真实令牌才能走认证链路",
            file=sys.stderr,
        )
        return EXIT_ERROR
    payload = smoke(ApiRuntime(config, root=root), token=token)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"live: {payload['live']['status']}")
        print(f"ready: {payload['ready']['state']}（{payload['ready']['detail']}）")
        print(f"evaluate: {payload['evaluate']['decision']}（{payload['evaluate']['rules']} 条规则）")
        print(f"retrieve: {payload['retrieve']['status']}")
    return EXIT_OK if payload["ok"] else EXIT_UNHEALTHY


def _seal(args: argparse.Namespace, config: ApiConfig, root: Path) -> int:
    """观测日志的对外锚定：Phase 4 的摘要链发现不了"删尾部/整链重写"。

    Phase 7 的做法是把链末值**发布到日志之外**（由操作者决定放在哪），
    之后任何改动都会与锚不符。锚本身被改掉的情况不在本命令的能力范围内——
    这正是"锚必须与日志分离存放"的原因，也是文档里写明的边界。
    """

    from .observability import RequestLog, seal_audit, verify_seal

    log = RequestLog(
        None if config.audit.path is None else (root / config.audit.path),
        enabled=config.audit.enabled,
        workspace=root,
    )
    if args.verify:
        target = Path(args.verify)
        if not target.is_absolute():
            target = root / target
        if not target.is_file():
            print(f"policy-api: 锚定文件不存在：{target.name}", file=sys.stderr)
            return EXIT_ERROR
        seal = json.loads(target.read_text(encoding="utf-8"))
        issues = verify_seal(log, seal)
        if args.json:
            print(json.dumps({"ok": not issues, "issues": list(issues), "seal": seal}, ensure_ascii=False, indent=2))
        elif issues:
            print("[seal] %d 处不一致：" % len(issues))
            for item in issues:
                print("  ! " + item)
        else:
            print(f"[seal] 与锚一致（{seal.get('records')} 条记录，链末值 {seal.get('chain_digest')}）")
        return EXIT_OK if not issues else EXIT_UNHEALTHY

    seal = seal_audit(log)
    payload = json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        target = Path(args.out)
        if not target.is_absolute():
            target = root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8", newline="\n")
        print(f"[seal] 已写出锚：{target.name}（{seal['records']} 条记录）")
    else:
        print(payload, end="")
    return EXIT_OK


def _self_check(args: argparse.Namespace, config: ApiConfig, root: Path) -> int:
    from .contract import self_check

    report = self_check(ApiRuntime(config, root=root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("配置版本: " + config.schema_version)
        print("租户: " + ", ".join(report["tenants"]) + ("" if report["tenants"] else "<none>"))
        print("客户端: " + str(report["clients"]))
        print("readiness: " + report["readiness"]["state"] + "（" + report["readiness"]["detail"] + "）")
        for item in report["checks"]:
            mark = "ok  " if item["ok"] else "FAIL"
            print(f"  [{mark}] {item['check']}: {item['detail']}")
    return EXIT_OK if report["ok"] else EXIT_UNHEALTHY


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(argv)
    except ApiError as error:
        print(f"policy-api: {error.kind}: {error.detail}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - 交互式中断
        return 130


if __name__ == "__main__":
    # `python -m policy_api.cli ...` 的入口。缺了这一段，模块会**静默地什么都不做**
    # 并以 0 退出——README 与 CI 里写的都是这条命令，装成"跑过了"比报错更危险。
    raise SystemExit(main())
