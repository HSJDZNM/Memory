"""D 门 2 评分器的确定性 sha256 清单生成器。

输入 = scorer.yaml 的 manifest.inputs（文件或目录，仓库相对 POSIX 路径；目录用结尾的 / 表示）。
输出 = 每行「<sha256>  <仓库相对路径>」，按路径升序、UTF-8 无 BOM / LF / 单尾换行，不含 manifest.sha256 自身。

用法：

    python <scorer>/make_manifest.py                 # 生成 <scorer>/manifest.sha256
    python <scorer>/make_manifest.py --print          # 只把清单文本打到 stdout（不写文件）
    python <scorer>/make_manifest.py --check          # 比对现有清单；pending（声明了但还没生成）不算失败
    python <scorer>/make_manifest.py --check --strict # 冻结门禁：pending 也算失败

--check 的四类结论：

    bad       清单里的文件哈希不符                 => 失败（换过内容）
    missing   清单里的文件已经不存在               => 失败（冻结后删文件也是漂移）
    unlisted  声明的输入里出现了清单没有的文件     => 失败（新增文件 = 换了输入）
    pending   声明的输入还不存在（hidden/ 未落盘） => 不算失败；--strict 下算失败

为什么 pending 单独成一档：hidden/ 由另一个会话在写，评分器骨架先落地。把「还没生成」记成失败会让
每一次 --check 都红、从而失去信号；把它记成通过又会让「冻结前必须全部存在」变成一句空话。所以它自成一档，
默认只报告，冻结时由 --strict 与 scorer.yaml 的 freeze.prerequisites 一起把它变成硬门禁。

本脚本不含时戳、不含 run id、不写绝对路径：相同输入的两次运行逐字节相同。
路径排序用 POSIX 字符串升序（Windows 与 POSIX 上同一份清单，不受文件系统大小写/分隔符影响）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

SCORER_DIR = Path(__file__).resolve().parent
SPEC_PATH = SCORER_DIR / "scorer.yaml"
DEFAULT_OUT = SCORER_DIR / "manifest.sha256"

#: 找不到 .git / policies+src 时的兜底：scorer 目录向上 8 层是仓库根。
FALLBACK_PARENTS = 8


def repo_root(start: Path) -> Path:
    """从本脚本位置向上回溯到仓库根（含 .git，或同时含 policies/ 与 src/）。"""
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
        if (candidate / "policies").is_dir() and (candidate / "src").is_dir():
            return candidate
    parents = start.parents
    if len(parents) > FALLBACK_PARENTS:
        return parents[FALLBACK_PARENTS]
    raise SystemExit("make_manifest: 找不到仓库根；用 --root 显式指定")


def load_spec(path: Path) -> Dict:
    """读 scorer.yaml。读不出来是用法错误（退出 2），不降级成空清单。"""
    try:
        import yaml
    except ImportError:
        raise SystemExit("make_manifest: 需要 PyYAML（用仓库的 .venv/Scripts/python.exe 跑）")
    if not path.is_file():
        raise SystemExit("make_manifest: 读不到 %s" % path.name)
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict) or "manifest" not in document:
        raise SystemExit("make_manifest: %s 里没有 manifest 段" % path.name)
    return document["manifest"]


def skip_names(spec: Dict) -> Tuple[set, Tuple[str, ...]]:
    """从 scorer.yaml 取跳过规则（跳过什么写在数据里，不藏在脚本里）。"""
    directories = {str(name) for name in spec.get("skip_dir_names", [])}
    suffixes = tuple(str(suffix) for suffix in spec.get("skip_suffixes", []))
    return directories, suffixes


def iter_input(root: Path, entry: str, directories: set, suffixes: Tuple[str, ...]) -> List[str]:
    """枚举一条声明输入覆盖的文件（仓库相对 POSIX 路径）。缺失 = 返回空列表。"""
    relative = entry.rstrip("/")
    target = root / relative
    if entry.endswith("/"):
        if not target.is_dir():
            return []
        found: List[str] = []
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = sorted(name for name in dirnames if name not in directories)
            for name in sorted(filenames):
                if suffixes and name.endswith(suffixes):
                    continue
                full = Path(dirpath) / name
                found.append(full.relative_to(root).as_posix())
        return found
    if not target.is_file():
        return []
    return [relative]


def digest_of(path: Path) -> str:
    """sha256(原始字节)；不做换行归一化（Windows 的 Get-FileHash 与 sha256sum 同值）。"""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def enumerate_files(root: Path, spec: Dict, out_path: Path) -> Tuple[Dict[str, str], List[str]]:
    """返回（路径 → sha256, pending 的声明顶）。自身（输出文件）永远不进清单。"""
    directories, suffixes = skip_names(spec)
    own = out_path.resolve()
    hashes: Dict[str, str] = {}
    pending: List[str] = []
    for entry in spec.get("inputs", []):
        relative = str(entry).rstrip("/")
        files = iter_input(root, str(entry), directories, suffixes)
        if not files:
            if not (root / relative).exists():
                pending.append(str(entry))
            continue
        for file in files:
            full = (root / file).resolve()
            if full == own:
                continue
            hashes[file] = digest_of(full)
    return hashes, pending


def render(hashes: Dict[str, str]) -> str:
    """清单文本：按路径升序、LF、单尾换行。"""
    lines = ["%s  %s" % (hashes[path], path) for path in sorted(hashes)]
    return "".join(line + "\n" for line in lines)


def combined_digest(text: str) -> str:
    """组合摘要 = sha256(清单文本字节)；每次 run 的 run-manifest 记这一份。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_manifest(text: str) -> Tuple[Dict[str, str], List[str]]:
    """解析清单；返回（路径 → sha256, 格式错误的行）。"""
    entries: Dict[str, str] = {}
    problems: List[str] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        digest, separator, path = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not path:
            problems.append("第 %d 行不是「<sha256>  <path>」：%r" % (number, line))
            continue
        entries[path] = digest
    return entries, problems


def report_line(kind: str, path: str, detail: str = "") -> str:
    """一行结论；kind 是固定的四种之一（bad / missing / unlisted / pending）。"""
    return "%-8s  %s%s" % (kind, path, ("（%s）" % detail) if detail else "")


def run_check(root: Path, spec: Dict, out_path: Path, strict: bool) -> int:
    """比对现有清单。返回退出码：0 = 一致（或只有 pending），1 = 有差异。"""
    if not out_path.is_file():
        print("RESULT: FAIL（读不到 %s；先跑一次生成）" % out_path.name)
        return 1
    text = out_path.read_text(encoding="utf-8")
    recorded, malformed = parse_manifest(text)
    problems: List[str] = list(malformed)
    for path, expected in sorted(recorded.items()):
        full = root / path
        if not full.is_file():
            problems.append(report_line("missing", path, "冻结清单里的文件不存在"))
            continue
        actual = digest_of(full)
        if actual != expected:
            problems.append(report_line("bad", path, "sha256 不符：清单 %s / 实际 %s" % (expected[:12], actual[:12])))
    hashes, pending = enumerate_files(root, spec, out_path)
    for path in sorted(hashes):
        if path not in recorded:
            problems.append(report_line("unlisted", path, "新增文件：冻结清单里没有它，重新生成后才算冻结"))
    for entry in pending:
        problems.append(report_line("pending", entry, "声明了但还没生成"))
    for line in problems:
        print(line)
    failures = [line for line in problems if not line.startswith("pending")]
    if failures:
        print("RESULT: FAIL（%d 条差异 / %d 条 pending）" % (len(failures), len(pending)))
        return 1
    if pending and strict:
        print("RESULT: FAIL（--strict：%d 条 pending——冻结前必须全部存在）" % len(pending))
        return 1
    print("RESULT: PASS（%d 个文件逐字节一致，%d 条 pending）" % (len(recorded), len(pending)))
    return 0


def run_write(root: Path, spec: Dict, out_path: Path, to_stdout: bool) -> int:
    """生成清单并写盘（--print 时只打 stdout，不写文件）。"""
    hashes, pending = enumerate_files(root, spec, out_path)
    if not hashes:
        print("make_manifest: 一个文件都没枚举到；拒绝写空清单（空清单不是「全部一致」）", file=sys.stderr)
        return 1
    text = render(hashes)
    if to_stdout:
        sys.stdout.write(text)
        sys.stdout.flush()
        stream = sys.stderr
    else:
        out_path.write_bytes(text.encode("utf-8"))
        stream = sys.stdout
        print("wrote %s（%d 个文件）" % (out_path.relative_to(root).as_posix(), len(hashes)), file=stream)
    print("combined_digest: sha256:%s" % combined_digest(text), file=stream)
    if pending:
        print("pending: %d 条声明的输入还不存在（冻结前必须全部存在）" % len(pending), file=stream)
        for entry in pending:
            print("  pending  %s" % entry, file=stream)
    else:
        print("pending: 0", file=stream)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """入口。退出码：0 = 成功 / 一致；1 = 有差异或写不出来；2 = 用法错误。"""
    parser = argparse.ArgumentParser(
        prog="make_manifest",
        description="D 门 2 评分器的确定性 sha256 清单生成器（输入取自 scorer.yaml 的 manifest.inputs）",
    )
    parser.add_argument("--root", type=Path, default=None, help="仓库根（默认从本脚本位置向上找 .git / policies+src）")
    parser.add_argument("--out", type=Path, default=None, help="清单输出路径（默认 <scorer>/manifest.sha256）")
    parser.add_argument("--print", dest="to_stdout", action="store_true", help="只把清单文本打到 stdout，不写文件")
    parser.add_argument("--check", action="store_true", help="比对现有清单（不写文件）")
    parser.add_argument("--strict", action="store_true", help="配合 --check：pending 也算失败（冻结门禁用）")
    arguments = parser.parse_args(argv)

    root = (arguments.root or repo_root(SCORER_DIR)).resolve()
    out_path = (arguments.out or DEFAULT_OUT).resolve()
    spec = load_spec(SPEC_PATH)
    if arguments.check and arguments.to_stdout:
        print("make_manifest: --check 与 --print 不能同时用（一个读、一个写）", file=sys.stderr)
        return 2
    try:
        out_path.relative_to(root)
    except ValueError:
        print("make_manifest: --out 必须在仓库内（清单里只有仓库相对路径）", file=sys.stderr)
        return 2
    if arguments.check:
        return run_check(root, spec, out_path, arguments.strict)
    return run_write(root, spec, out_path, arguments.to_stdout)


if __name__ == "__main__":
    raise SystemExit(main())
