from __future__ import annotations

import sys


def log(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", file=sys.stderr, flush=True)
