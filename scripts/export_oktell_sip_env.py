"""Build OKTELL SIP env lines from the vendor Excel. Do not commit the output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def rows_from_xlsx(path: Path) -> list[tuple[str, str]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit("pip install openpyxl") from exc
    book = openpyxl.load_workbook(path, data_only=True)
    sheet = book.active
    mapping: list[tuple[str, str]] = []
    for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        if not row or index == 1:
            continue
        login, password = row[0], row[1]
        if login is None or password is None:
            continue
        mapping.append((str(login).strip(), str(password)))
    return mapping


def env_text(pairs: list[tuple[str, str]], *, count: int) -> str:
    chosen = pairs[: max(count, 1)]
    payload = {user: password for user, password in chosen}
    return "\n".join(
        [
            "OKTELL_LISTEN_MODE=sip",
            "OKTELL_SIP_SERVER=10.1.1.31",
            "OKTELL_SIP_DOMAIN=dev-qms.onedemoserver.online",
            "OKTELL_SIP_PROXY=10.1.1.31",
            "OKTELL_SIP_USER_START=2001",
            f"OKTELL_SIP_USER_COUNT={len(chosen)}",
            f"OKTELL_SIP_PASSWORDS_JSON={json.dumps(payload, ensure_ascii=False)}",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=8)
    args = parser.parse_args()
    if not args.xlsx.exists():
        raise SystemExit(f"file not found: {args.xlsx}")
    text = env_text(rows_from_xlsx(args.xlsx), count=args.count)
    args.output.write_text(text, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    sys.exit(main())
