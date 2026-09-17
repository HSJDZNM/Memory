"""从 pip 的安装报告生成带哈希的依赖锁文件。

用法（PowerShell）：

    python -m pip install --dry-run --report .tmp/pip-report.json -r requirements.in
    python tools/lock_requirements.py .tmp/pip-report.json requirements.lock

报告来自真实解析结果，因此锁文件里的版本与哈希都可在干净环境复现。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REQUIREMENTS_IN = Path("requirements.in")
HEADER_LINES = (
    "# 由 tools/lock_requirements.py 生成，请勿手改。",
    "# 重新生成：见 tools/lock_requirements.py 的模块说明。",
)


def requirements_digest() -> str:
    text = REQUIREMENTS_IN.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def lock_entries(report: dict) -> list[tuple[str, list[str]]]:
    """把 pip 报告转换成排序后的 (小写包名, 锁文件行) 列表。"""

    entries: list[tuple[str, list[str]]] = []
    for item in report["install"]:
        metadata = item["metadata"]
        lines = [f"{metadata['name']}=={metadata['version']}"]
        hashes = item.get("download_info", {}).get("archive_info", {}).get("hashes", {})
        for algorithm in sorted(hashes):
            lines.append("    " + "--hash" + "=" + algorithm + ":" + hashes[algorithm])
        entries.append((str(metadata["name"]).lower(), lines))
    entries.sort(key=lambda entry: entry[0])
    return entries


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    report_path = Path(argv[1])
    output_path = Path(argv[2])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    entries = lock_entries(report)
    if not entries:
        print("报告里没有要安装的包：请确认 requirements.in 未被当前环境全部满足", file=sys.stderr)
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
