"""只读校验工具：用 shop.config.load_config 检查一个 v2 配置文件。

用法：python tools/check_config.py --config config/app.yaml
合法退出码 0（stdout 一行）；非法退出码 1（stderr 一行原因）；不写被校验的文件。
"""

import argparse
import sys
from pathlib import Path

# 以脚本方式从项目根运行时 sys.path[0] 是 tools/：先把 <项目根>/src 插进来，再 import shop。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shop.config import load_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """校验 --config 指向的配置文件：合法返回 0，非法返回 1。"""
    parser = argparse.ArgumentParser(description="校验 v2 应用配置")
    parser.add_argument("--config", required=True, help="配置文件路径")
    args = parser.parse_args(argv)
    path = Path(args.config)
    try:
        load_config(path)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write("配置合法：" + path.name + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
