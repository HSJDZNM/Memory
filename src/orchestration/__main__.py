"""`python -m orchestration` 等价于 `python -m orchestration.cli`。"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
