"""控制面针脚的命令行入口（方案 §3.1 / §5.3）。

三条用法：

    python -m provenance.cli digest --root . --declaration <file> [--platform <file>] [--json]
    python -m provenance.cli seal --root . --declaration <file> [--platform <file>]
                                 [--out <receipt.json>] [--landing <state>] -- <命令> [参数...]
    python -m provenance.cli wiring-scope --check [--path adapters/wiring-scope.yaml] [--json]

退出码（方案 §5.3，**不与 Hook 的 exit 2 复用**）：

    0 = 判据 pass 且封条一致
    1 = 判据 fail（子进程非 0；或 wiring-scope 的边界声明**内容**不合法）
    2 = 用法错误：参数不可用——声明文件 / --platform 读不到、判据命令起不来；
        digest 与 seal 对同一种参数不可用必须给同一个码
    3 = 封条失效：external_write（pre != post）或 unprovable（读不到声明的东西）
        —— 「本轮结论全部作废」，不许当成 pass

R-e 的落地形态就是这里的 seal：任何被判 pass 的检查都必须交出 referenced_inputs_digest，
而且它必须与收尾时实测的一致；给不出（声明空壳、命中不到文件）或对不上，都是 3。
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import worktree
from .wiring_scope import WiringScopeError, load_wiring_scope

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SEAL = 3

RECEIPT_SCHEMA_VERSION = "1.0"
DEFAULT_WIRING_SCOPE = "adapters/wiring-scope.yaml"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _display(path: Path | str, root: Path) -> str:
    """回执里的路径一律相对根渲染：绝对路径不进产物（AGENTS 第 19 条同一口径）。"""

    target = Path(path)
    try:
        return target.resolve().relative_to(root.resolve()).as_posix() or "."
    except (OSError, ValueError):
        return target.as_posix()


def _argv_display(argv: Sequence[str]) -> list:
    """把解释器本身渲染成 python：回执里不留本机的绝对路径。"""

    out = []
    for index, item in enumerate(argv):
        if index == 0 and Path(item).name.lower().startswith("python"):
            out.append("python")
        else:
            out.append(item)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m provenance.cli",
        description="控制面针脚：判据级封条、轮次级封条与边界声明校验。",
    )
    sub = parser.add_subparsers(dest="command_name", required=True)

    digest = sub.add_parser("digest", help="打印四个针脚里的三个摘要（判据 / 轮次 / 平台）")
    digest.add_argument("--root", default=".")
    digest.add_argument("--declaration", required=True)
    digest.add_argument("--platform", default=None)
    digest.add_argument("--json", action="store_true")

    seal = sub.add_parser("seal", help="seal(pre) -> 跑判据 -> seal(post)，写回执")
    seal.add_argument("--root", default=".")
    seal.add_argument("--declaration", required=True)
    seal.add_argument("--platform", default=None)
    seal.add_argument("--out", default=None, help="回执路径（不给就只打印）")
    seal.add_argument("--landing", default="landed_unverified")
    seal.add_argument("--peer-evidence", default=None, help="landed_peer_verified 的证据 JSON")
    seal.add_argument("rest", nargs=argparse.REMAINDER, help="-- 之后的判据命令")

    scope = sub.add_parser("wiring-scope", help="校验边界声明 adapters/wiring-scope.yaml")
    scope.add_argument("--check", action="store_true", help="只校验（默认行为）")
    scope.add_argument("--path", default=DEFAULT_WIRING_SCOPE)
    scope.add_argument("--json", action="store_true")

    return parser


def _emit(payload: Dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        print(f"{key}: {json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}")


def _run_digest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    # 声明文件本身不可用 = 用法错误（与 seal 同一口径）：调用方按退出码分流时，
    # 同一个失败模式不许在这里是 3、在那里是 2。
    try:
        declaration = worktree.load_declaration(args.declaration)
        platform_declaration = (
            worktree.load_declaration(args.platform)
            if args.platform
            else declaration
        )
    except worktree.UnprovableError as error:
        print(f"用法错误：{error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        referenced = worktree.referenced_inputs_digest(root, declaration)
        workspace = worktree.workspace_tree_digest(root)
        platform = worktree.platform_revision(root, platform_declaration)
    except worktree.UnprovableError as error:
        print(f"unprovable: {error}", file=sys.stderr)
        return EXIT_SEAL
    _emit(
        {
            "referenced_inputs_digest": referenced.sha256,
            "workspace_tree_digest": workspace.sha256,
            "platform_revision": platform.sha256,
            "referenced_files": referenced.files,
            "workspace_files": workspace.files,
            "platform_files": platform.files,
        },
        as_json=args.json,
    )
    return EXIT_PASS


def _run_seal(args: argparse.Namespace) -> int:
    root = Path(args.root)
    argv = list(args.rest)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("用法错误：seal 需要一条判据命令（写在 -- 之后）", file=sys.stderr)
        return EXIT_USAGE

    try:
        declaration = worktree.load_declaration(args.declaration)
    except worktree.UnprovableError as error:
        print(f"用法错误：{error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        # --platform 与 --declaration 是同一类输入（都是命令行给的声明文件）：它读不到
        # 同样是用法错误。不接住的话，裸 traceback 会让进程用解释器的默认退出码 1 结束——
        # 而 1 的含义是"判据跑完且是红的"，这里连判据都还没跑。
        platform_declaration = (
            worktree.load_declaration(args.platform) if args.platform else declaration
        )
    except worktree.UnprovableError as error:
        print(f"用法错误：{error}", file=sys.stderr)
        return EXIT_USAGE

    peer_evidence: Optional[Dict[str, Any]] = None
    if args.peer_evidence:
        try:
            parsed = json.loads(Path(args.peer_evidence).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(f"用法错误：peer-evidence 读不了（{error}）", file=sys.stderr)
            return EXIT_USAGE
        # json.loads 可以返回任何 JSON 类型：非对象会在下游按映射取键时抛 AttributeError
        # （裸 traceback + 解释器默认退出码 1），而 1 的含义是"判据跑完且是红的"——
        # 这里连判据都还没跑。信任边界上先证明它是对象。
        if not isinstance(parsed, dict):
            print(
                "用法错误：peer-evidence 必须是 JSON 对象，得到 "
                f"{type(parsed).__name__}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        peer_evidence = parsed
    try:
        landing = worktree.resolve_landing_state(args.landing, peer_evidence=peer_evidence)
    except worktree.LandingStateError as error:
        print(f"用法错误：{error}", file=sys.stderr)
        return EXIT_USAGE

    receipt: Dict[str, Any] = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "at": _utc_now(),
        "root": _display(root, root),
        "declaration": {
            "path": _display(args.declaration, root),
            "entries": list(declaration),
            "platform_entries": list(platform_declaration),
        },
        "landing_state": landing,
    }

    try:
        pre = worktree.seal(root, declaration, platform_declaration)
    except worktree.UnprovableError as error:
        receipt.update({"state": "unprovable", "error": str(error)})
        return _finish_seal(args, receipt, EXIT_SEAL)

    try:
        completed = subprocess.run(argv, cwd=str(root), check=False)
    except OSError as error:
        # 判据命令根本没跑起来（命令拼错 / 不可执行 / 工作目录在 pre 与 spawn 之间消失）。
        # 这不是"判据 fail"——退出码 1 的含义是"跑完了、是红的"；也不能让 Python 的默认
        # 退出码替我们回答（§52：异常路径要归因到真正的那一侧）。
        if not Path(root).is_dir():
            receipt.update(
                {"state": "unprovable", "error": f"判据命令的工作目录不见了：{root}"}
            )
            return _finish_seal(args, receipt, EXIT_SEAL)
        print(
            f"用法错误：判据命令无法启动（{type(error).__name__}: {error}）；"
            "判据没有运行，本轮没有结论",
            file=sys.stderr,
        )
        return EXIT_USAGE
    receipt["command"] = {"argv": _argv_display(argv), "exit_code": completed.returncode}

    try:
        post = worktree.seal(root, declaration, platform_declaration)
    except worktree.UnprovableError as error:
        receipt.update({"state": "unprovable", "error": str(error)})
        return _finish_seal(args, receipt, EXIT_SEAL)

    comparison = worktree.compare_seals(pre, post)
    receipt.update(
        {
            "state": comparison.state,
            "referenced_inputs_digest": post.referenced.sha256,
            "workspace_tree_digest": post.workspace.sha256,
            "platform_revision": post.platform.sha256,
            "referenced_files": post.referenced.files,
            "workspace_files": post.workspace.files,
            "differences": comparison.differences,
            "workspace_excludes": list(post.excludes),
        }
    )
    if comparison.state != "pass":
        # pre != post：本轮结论全部作废（方案 §5.3），退出码 3 优先于判据自身的红绿。
        return _finish_seal(args, receipt, EXIT_SEAL)
    if completed.returncode != 0:
        return _finish_seal(args, receipt, EXIT_FAIL)
    return _finish_seal(args, receipt, EXIT_PASS)


def _finish_seal(args: argparse.Namespace, receipt: Dict[str, Any], code: int) -> int:
    if args.out:
        # 给了 --out 就把回执写文件、stdout 留给判据命令自己：两者混在一个流里，
        # 读的人要靠猜哪几行是回执（子进程的输出也在这个 stdout 上）。
        target = Path(args.out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="",
            )
        except OSError as error:
            # 回执写不出去时不能用判据的结论退出码：1 的含义是"判据跑完且是红的"，
            # 而这里的问题在写文件这一侧（目录、权限、只读盘）。结论行照样打出来，
            # 读的人仍然能拿到判据的结果，只是回执没有落地。
            print(
                f"用法错误：回执写不出去（{target}：{type(error).__name__}: {error}）",
                file=sys.stderr,
            )
            print(f"seal state: {receipt.get('state')} (exit {EXIT_USAGE})", file=sys.stderr)
            return EXIT_USAGE
        print(f"receipt: {_display(target, Path(args.root))}", file=sys.stderr)
    else:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"seal state: {receipt.get('state')} (exit {code})", file=sys.stderr)
    return code


def _run_wiring_scope(args: argparse.Namespace) -> int:
    try:
        scope = load_wiring_scope(args.path)
    except WiringScopeError as error:
        # 失败路径也必须看 --json：否则要解析错误的那一方，恰好拿到的是人类可读格式。
        _emit({"result": "fail", "error": str(error)}, as_json=args.json)
        return EXIT_FAIL
    _emit({"result": "ok", **scope.as_json()}, as_json=args.json)
    return EXIT_PASS


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command_name == "digest":
        return _run_digest(args)
    if args.command_name == "seal":
        return _run_seal(args)
    if args.command_name == "wiring-scope":
        return _run_wiring_scope(args)
    print(f"用法错误：未知子命令 {args.command_name!r}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
