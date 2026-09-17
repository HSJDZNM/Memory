"""支持 python -m enforcement：等价于 python -m enforcement.cli。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
