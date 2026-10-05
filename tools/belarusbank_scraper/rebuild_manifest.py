"""Deduplicate manifest.jsonl keeping the latest row per URL."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    path = Path(__file__).resolve().parents[2] / "local" / "kb" / "belarusbank" / "manifest.jsonl"
    if not path.exists():
        print("no manifest")
        return 1
    latest: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            url = row.get("url")
            if url:
                latest[url] = row
    bak = path.with_suffix(".jsonl.bak")
    path.replace(bak)
    with path.open("w", encoding="utf-8") as fh:
        for row in latest.values():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"rewrote {len(latest)} unique URLs (backup {bak.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
