"""从 pip 的安装报告生成带哈希的依赖锁文件。

用法（PowerShell）：

    python -m pip install --dry-run --report .tmp/pip-report.json -r requirements.in
    python tools/lock_requirements.py .tmp/pip-report.json requirements.lock

报告来自真实解析结果，因此锁文件里的版本与哈希都可在干净环境复现。

**必须在干净环境里跑那条 pip 命令**：`--dry-run --report` 只列「这次会安装」的包，
当前环境已满足的依赖不会出现——那样生成的锁会**静默缺包**。工具因此拒绝出锁并点名缺席的包。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# 锚在仓库根，不跟 cwd：从别的目录跑（例如 `cd tools; python lock_requirements.py …`）时
# 旧写法会 a) 直接 FileNotFoundError，或 b) 读到一个**不相干的** requirements.in，
# 于是锁文件头部记的摘要描述的不是这次真正用的那份声明。与 check_repo_consistency.py 同口径。
ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_IN = ROOT / "requirements.in"
HEADER_LINES = (
    "# 由 tools/lock_requirements.py 生成，请勿手改。",
    "# 重新生成：见 tools/lock_requirements.py 的模块说明。",
)


def requirements_digest() -> str:
    text = REQUIREMENTS_IN.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def normalized(name: str) -> str:
    """PEP 503 归一化：判「同一个包」时不分大小写与 -/_/. 的写法差异。"""

    return name.strip().lower().replace("_", "-").replace(".", "-")


def declared_names() -> list[str]:
    """`requirements.in` 里声明的直接依赖名（归一化、去重、保序）。"""

    names: list[str] = []
    for raw in REQUIREMENTS_IN.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = line.split("[", 1)[0].split(";", 1)[0]
        for separator in ("<", ">", "=", "!", "~", " "):
            name = name.split(separator, 1)[0]
        if name:
            key = normalized(name)
            if key not in names:
                names.append(key)
    return names


def missing_declared(report: dict) -> list[str]:
    """报告里**缺席**的声明依赖（排序后的归一化名）。

    `pip install --dry-run --report` 只列「这次会安装」的包：**当前环境已满足**的依赖不会出现。
    于是从「只装了一部分」的环境生成的报告会让锁**静默缺包**——打印的包数看不出来，
    而这份锁是给干净环境 `pip install --require-hashes` 用的。缺席即拒绝出锁。
    """

    present: set[str] = set()
    for item in report["install"]:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if isinstance(metadata, dict) and isinstance(metadata.get("name"), str):
            present.add(normalized(metadata["name"]))
    return sorted({name for name in declared_names() if name not in present})


class LockError(RuntimeError):
    """锁文件的输入不满足「每条 pin 都带哈希」这个前提。"""


def lock_entries(report: dict) -> list[tuple[str, list[str]]]:
    """把 pip 报告转换成排序后的 (小写包名, 锁文件行) 列表。

    **没有哈希的条目直接报错**：本文件产出的锁是「每条 pin 都带哈希」的那一种（头部就写着
    --require-hashes 的用法）。可编辑安装 / VCS / 本地路径在 pip 报告里带的是 dir_info /
    vcs_info 而不是 archive_info.hashes，旧写法照样把它写成一条**裸 name==version**——
    锁于是混着「带哈希」与「不带哈希」两种行：pip install --require-hashes 会整份拒绝，
    而读文件的人看不出哪一条没被校验。宁可不出锁，也不出一份「看起来带了哈希」的锁。
    """

    entries: list[tuple[str, list[str]]] = []
    unhashed: list[str] = []
    for item in report["install"]:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict) or "name" not in metadata or "version" not in metadata:
            raise LockError(
                "pip 报告里有形状不对的条目（缺 metadata.name / metadata.version）：" + repr(item)[:120]
            )
        archive = item.get("download_info", {}).get("archive_info", {}) or {}
        hashes = dict(archive.get("hashes", {}) or {})
        if not hashes and isinstance(archive.get("hash"), str):
            # 老版本 pip 只给**单数** archive_info.hash（形如 sha256=<hex>）：认它，
            # 别把「另一种写法」读成「没有哈希」。
            algorithm, _, value = archive["hash"].partition("=")
            if algorithm and value:
                hashes = {algorithm: value}
        if not hashes:
            unhashed.append(str(metadata.get("name", "?")))
            continue
        lines = [f"{metadata['name']}=={metadata['version']}"]
        for algorithm in sorted(hashes):
            lines.append("    " + "--hash" + "=" + algorithm + ":" + hashes[algorithm])
        # pip 只把同一条**逻辑行**上的 --hash 绑定到依赖：续行必须用行尾反斜杠。
        lines = [line + " \\" for line in lines]
        lines[-1] = lines[-1].removesuffix(" \\")
        entries.append((str(metadata["name"]).lower(), lines))
    if unhashed:
        raise LockError(
            "报告里有 " + str(len(unhashed)) + " 个条目没有哈希（可编辑 / VCS / 本地安装，或报告形态不认识）："
            + ", ".join(sorted(unhashed)) + "；本锁要求每条 pin 都带哈希，"
            "先改 requirements.in 或换一份报告",
        )
    entries.sort(key=lambda entry: entry[0])
    return entries


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    report_path = Path(argv[1])
    output_path = Path(argv[2])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as error:
        print("读不了 pip 报告 " + str(report_path) + "：" + str(error), file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print("pip 报告不是合法 JSON（" + str(report_path) + "）：" + str(error), file=sys.stderr)
        return 2
    if not isinstance(report, dict) or not isinstance(report.get("install"), list):
        # 形状不对时 `report["install"]` / `item["metadata"]` 会以 KeyError / TypeError 逃出去：
        # 文件/JSON/形状三类错误都该走"友好消息 + 退出码 2"，而不是裸 traceback。
        print(
            "pip 报告的顶层形状不对（需要含 install 数组的对象）：" + str(report_path),
            file=sys.stderr,
        )
        return 2
    try:
        entries = lock_entries(report)
    except LockError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not entries:
        print("报告里没有要安装的包：请确认 requirements.in 未被当前环境全部满足", file=sys.stderr)
        return 2
    missing = missing_declared(report)
    if missing:
        print(
            "pip 报告里缺席 "
            + str(len(missing))
            + " 个 requirements.in 声明的直接依赖："
            + ", ".join(missing)
            + "。`pip install --dry-run --report` 不会列出**当前环境已满足**的依赖，所以这份报告来自「只装了一部分」的环境时，生成的锁会静默缺包（打印的包数看不出来）。请在干净环境里重跑那条 pip 命令再生成。",
            file=sys.stderr,
        )
        return 2

    body: list[str] = list(HEADER_LINES)
    body.append("#")
    body.append("# requirements.in sha256: " + requirements_digest())
    body.append("")
    for _name, lines in entries:
        body.extend(lines)
        body.append("")

    text = chr(10).join(body).rstrip() + chr(10)
    output_path.write_text(text, encoding="utf-8", newline=chr(10))
    print(f"已写入 {output_path}，共 {len(entries)} 个包")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
