"""`python -m adapters` 的入口：等价于 `python -m adapters.cli`。"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
