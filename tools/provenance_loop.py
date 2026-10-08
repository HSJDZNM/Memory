"""控制面封条的闭环：R-e 的可执行读数（方案 §4 台阶 0、§5.2 R-e）。

R-e 的原文是：**任何被判 pass 的检查必须交出 referenced_inputs_digest，且与验收结束时
实测一致；给不出或不一致 → external_write、退 3、本轮结论全部作废。** 本工具把这句话跑
成五个场景，每个场景都记「期望 / 实测 / 退出码」：

1. pass-sealed-check    真判据（pytest 跑本台阶的单测）+ 真声明 → 状态 pass、退出 0；
2. external-write       判据运行期间往**声明的输入**里写一笔 → 状态 external_write、退出 3；
3. unprovable-decl    　声明里有一条 glob 命中不到任何文件 → 状态 unprovable、退出 3；
4. no-declaration       声明只有注释（= 给不出 referenced_inputs_digest）→ 状态 unprovable、
                        退出 3，而且回执里**不许**出现 referenced_inputs_digest（反退化）；
5. self-check-comparator **仪器自证**：同一个场景（建树 → 种一次未声明写者 → 两次封条）
                        跑两遍——真比对器给 external_write、恒 pass 的替身给 pass——
                        证明上面那条红真的来自"比对"这一步；并额外要求红可归因到那笔写入
                        （differences.modified == declared/a.txt）。读数全部来自真的调用
                        （AGENTS 第 45 条：自己的仪器也要能失败）。

产物：.tmp/artifacts/provenance-loop-result.json（读数）；退出码 0 = 五个场景全部符合期望。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
SCRATCH = REPO / ".tmp" / "provenance-loop"
ARTIFACT = REPO / ".tmp" / "artifacts" / "provenance-loop-result.json"
SCHEMA_VERSION = "1.0"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from provenance import worktree  # noqa: E402 - 先补 sys.path 再导入

EXIT_PASS = 0
EXIT_FAIL = 1


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _run_cli(argv: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "provenance.cli", *argv],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _make_tree(name: str) -> Path:
    tree = SCRATCH / "trees" / name
    if tree.exists():
        shutil.rmtree(tree)
    _write(tree / "declared" / "a.txt", "alpha\n")
    _write(tree / "declared" / "b.txt", "beta\n")
    _write(tree / "other" / "c.txt", "gamma\n")
    return tree


def _writer_argv(target: Path) -> List[str]:
    """判据命令：往一个**声明的输入**里追加内容（= 运行期出现的未声明写者）。"""

    return [
        sys.executable,
        "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('changed\\n', encoding='utf-8')",
        str(target),
    ]


def _scenario(
    *,
    scenario_id: str,
    what: str,
    expected_state: str,
    expected_exit: int,
    receipt: Dict[str, Any],
    exit_code: int,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observed_state = receipt.get("state")
    record: Dict[str, Any] = {
        "id": scenario_id,
        "what": what,
        "expected_state": expected_state,
        "expected_exit": expected_exit,
        "observed_state": observed_state,
        "observed_exit": exit_code,
        "differences": receipt.get("differences"),
        "ok": observed_state == expected_state and exit_code == expected_exit,
    }
    if extra:
        record.update(extra)
    return record


def scenario_pass_sealed_check() -> Dict[str, Any]:
    declarations = SCRATCH / "declarations"
    declaration = declarations / "pass.txt"
    platform = declarations / "platform.txt"
    _write(
        declaration,
        "# 判据级封条：这次检查声明它会读这些输入\nsrc/provenance/*.py\n"
        "tests/unit/test_provenance_worktree.py\n",
    )
    _write(platform, "src/provenance/*.py\ntools/provenance_loop.py\n")
    receipt_path = SCRATCH / "receipts" / "pass.json"
    if receipt_path.exists():
        receipt_path.unlink()
    completed = _run_cli(
        [
            "seal",
            "--root", ".",
            "--declaration", str(declaration),
            "--platform", str(platform),
            "--out", str(receipt_path),
            "--",
            sys.executable, "-m", "pytest", "-q", "tests/unit/test_provenance_worktree.py",
        ]
    )
    return _scenario(
        scenario_id="pass-sealed-check",
        what="真判据（本台阶单测）跑完，声明输入与工作树都没有变",
        expected_state="pass",
        expected_exit=EXIT_PASS,
        receipt=_read_json(receipt_path),
        exit_code=completed.returncode,
        extra={"receipt": str(receipt_path.relative_to(REPO).as_posix())},
    )


def scenario_external_write() -> Dict[str, Any]:
    tree = _make_tree("external-write")
    declaration = SCRATCH / "declarations" / "external-write.txt"
    _write(declaration, "declared/*.txt\n")
    receipt_path = SCRATCH / "receipts" / "external-write.json"
    completed = _run_cli(
        [
            "seal",
            "--root", str(tree),
            "--declaration", str(declaration),
            "--out", str(receipt_path),
            "--",
            *_writer_argv(tree / "declared" / "a.txt"),
        ]
    )
    return _scenario(
        scenario_id="external-write",
        what="判据运行期间往声明的输入里写一笔（未声明的写者）",
        expected_state="external_write",
        expected_exit=3,
        receipt=_read_json(receipt_path),
        exit_code=completed.returncode,
    )


def scenario_unprovable() -> Dict[str, Any]:
    tree = _make_tree("unprovable")
    declaration = SCRATCH / "declarations" / "unprovable.txt"
    _write(declaration, "declared/*.txt\nmissing/**/*.py\n")
    receipt_path = SCRATCH / "receipts" / "unprovable.json"
    completed = _run_cli(
        [
            "seal",
            "--root", str(tree),
            "--declaration", str(declaration),
            "--out", str(receipt_path),
            "--",
            *_writer_argv(tree / "declared" / "b.txt"),
        ]
    )
    return _scenario(
        scenario_id="unprovable-decl",
        what="声明里有一条 glob 命中不到任何文件：证明不了，不给 pass",
        expected_state="unprovable",
        expected_exit=3,
        receipt=_read_json(receipt_path),
        exit_code=completed.returncode,
    )


def scenario_no_declaration() -> Dict[str, Any]:
    tree = _make_tree("no-declaration")
    declaration = SCRATCH / "declarations" / "empty.txt"
    _write(declaration, "# 只有注释：这份声明给不出 referenced_inputs_digest\n")
    receipt_path = SCRATCH / "receipts" / "no-declaration.json"
    completed = _run_cli(
        [
            "seal",
            "--root", str(tree),
            "--declaration", str(declaration),
            "--out", str(receipt_path),
            "--",
            sys.executable, "-c", "print('这条判据什么都不改')",
        ]
    )
    receipt = _read_json(receipt_path)
    record = _scenario(
        scenario_id="no-declaration",
        what="声明是空壳（只有注释）：给不出判据级封条，不许 pass",
        expected_state="unprovable",
        expected_exit=3,
        receipt=receipt,
        exit_code=completed.returncode,
    )
    record["digest_absent"] = "referenced_inputs_digest" not in receipt
    record["ok"] = bool(record["ok"]) and record["digest_absent"]
    return record


def _self_check_comparison(compare, tree_name: str, declaration: List[str]):
    """同一个场景（建树 → 种一次未声明写者 → 两次封条）在**给定比对器**下的读数。

    仪器自证要的是"结论跟着比对器变"，所以比对器必须从参数进来：断言一个字符串常量
    （旧写法 `stub = "pass"`）恒真，证明不了任何事。
    """

    tree = _make_tree(tree_name)
    pre = worktree.seal(tree, declaration, declaration)
    _write(tree / "declared" / "a.txt", "changed\n")
    post = worktree.seal(tree, declaration, declaration)
    return compare(pre, post)


def _always_pass(_pre, _post):
    """恒 pass 的比对替身：红如果还在，就说明红不是比对这一步给出的。"""

    return worktree.SealComparison(state="pass", added=(), modified=(), removed=(),
                                   before={}, after={})


def scenario_self_check() -> Dict[str, Any]:
    declaration = ["declared/*.txt"]
    # 同一条路径跑两遍：真比对器 vs 恒 pass 替身。两边的读数都来自真的调用。
    real = _self_check_comparison(worktree.compare_seals, "self-check-real", declaration)
    stub = _self_check_comparison(_always_pass, "self-check-stub", declaration)
    ok = (
        real.state == "external_write"
        and real.differences["modified"] == ["declared/a.txt"]
        and stub.state == "pass"
    )
    return {
        "id": "self-check-comparator",
        "what": "把比对换成恒 pass 的替身，同一个场景不再报红——证明那条红来自比对本身；"
                "同时要求红可归因到种下的那次写入（declared/a.txt 被改）",
        "expected_state": "external_write",
        "expected_exit": None,
        "observed_state": real.state,
        "observed_exit": None,
        "comparator_state": real.state,
        "stub_state": stub.state,
        "differences": real.differences,
        "ok": ok,
    }


SCENARIOS = (
    scenario_pass_sealed_check,
    scenario_external_write,
    scenario_unprovable,
    scenario_no_declaration,
    scenario_self_check,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/provenance_loop.py")
    parser.add_argument("--out", default=str(ARTIFACT), help="读数 JSON 的落点")
    args = parser.parse_args(argv)

    SCRATCH.mkdir(parents=True, exist_ok=True)
    records = [scenario() for scenario in SCENARIOS]
    failed = [record for record in records if not record["ok"]]
    report = {
        "schema_version": SCHEMA_VERSION,
        "tree": ".",
        "scenarios": records,
        "result": "fail" if failed else "pass",
    }

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write(target, json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"{'场景':<24}{'期望':<18}{'实测':<18}{'退出码':<8}结论")
    for record in records:
        expected = f"{record['expected_state']}"
        observed = f"{record['observed_state']}"
        code = "-" if record["observed_exit"] is None else str(record["observed_exit"])
        print(f"{record['id']:<24}{expected:<18}{observed:<18}{code:<8}{'OK' if record['ok'] else 'FAIL'}")
    print(f"结果：{report['result']}（{len(records) - len(failed)}/{len(records)} 场景符合期望）")
    print(f"读数：{target}")
    return EXIT_PASS if not failed else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
