"""支持 python -m policy：等价于 python -m policy.check。"""

from __future__ import annotations

import sys

from .check import main

if __name__ == "__main__":
    sys.exit(main())
