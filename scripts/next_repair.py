#!/usr/bin/env python3
"""Print the next open competition repair items for a server worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=Path(__file__).resolve().parents[1] / "feedback" / "queue.json")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit 必须大于 0")
    with args.queue.open(encoding="utf-8") as handle:
        queue = json.load(handle)
    selected = queue.get("items", [])[: args.limit]
    print(json.dumps(selected, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
