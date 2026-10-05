"""Generate a customer-facing acceptance protocol from matrix.json.

Formal deliverable for приёмка (VII.2): pass/fail summary + signature blocks.
Run after acceptance suites have updated ``matrix.json`` statuses.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ACCEPTANCE_DIR = Path(__file__).resolve().parent
DEFAULT_MATRIX = ACCEPTANCE_DIR / "matrix.json"
DEFAULT_OUTPUT = ACCEPTANCE_DIR / "protocol.md"

STATUS_ORDER = ("pass", "fail", "pending", "skip")

MODULE_LABELS = {
    "sufler": "Суфлёр (телефония / подсказки)",
    "chat": "Онлайн-чат",
    "assistant": "ИИ-ассистент",
    "documents": "Распознавание документов",
    "integration": "Интеграции",
}

STATUS_LABELS = {
    "pass": "пройден",
    "fail": "не пройден",
    "pending": "не выполнен",
    "skip": "пропущен",
}


def load_matrix(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("matrix.json must be a JSON array of cases")
    cases: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each matrix entry must be an object")
        case_id = str(item.get("id", "")).strip()
        module = str(item.get("module", "")).strip()
        status = str(item.get("status", "pending")).strip().lower()
        if not case_id:
            raise ValueError("matrix entry missing id")
        if status not in STATUS_ORDER:
            raise ValueError(f"unsupported status for {case_id}: {status}")
        cases.append({"id": case_id, "module": module or "—", "status": status})
    return cases


def summarize(cases: list[dict[str, str]]) -> dict[str, Any]:
    by_status = Counter(case["status"] for case in cases)
    modules = sorted({case["module"] for case in cases})
    by_module: dict[str, Counter[str]] = {
        module: Counter(
            case["status"] for case in cases if case["module"] == module
        )
        for module in modules
    }
    return {
        "total": len(cases),
        "by_status": {status: by_status.get(status, 0) for status in STATUS_ORDER},
        "by_module": by_module,
        "modules": modules,
    }


def verdict(summary: dict[str, Any]) -> tuple[str, str]:
    """Return (code, human label) for overall protocol result."""
    counts = summary["by_status"]
    if counts.get("fail", 0) > 0:
        return "fail", "Приёмка не пройдена (есть fail)"
    if counts.get("pending", 0) > 0:
        return "in_progress", "Приёмка не завершена (есть pending)"
    if summary["total"] == 0:
        return "empty", "Матрица пуста"
    if counts.get("pass", 0) + counts.get("skip", 0) == summary["total"]:
        return "pass", "Приёмка пройдена"
    return "unknown", "Статус приёмки требует уточнения"


def _module_title(module: str) -> str:
    return MODULE_LABELS.get(module, module)


def render_protocol(
    cases: list[dict[str, str]],
    *,
    generated_on: date | None = None,
    matrix_path: Path | None = None,
    stand: str = "тест / приёмочный стенд AI Hub",
) -> str:
    """Render markdown protocol suitable for customer signature."""
    day = generated_on or date.today()
    summary = summarize(cases)
    verdict_code, verdict_label = verdict(summary)
    counts = summary["by_status"]
    source = matrix_path.name if matrix_path else "matrix.json"

    lines: list[str] = [
        "# Протокол приёмки программного обеспечения",
        "",
        "**Проект:** AI Hub / Суфлёр — ПО на базе ИИ для банковских процессов  ",
        "**Договор:** № 14-03/2026  ",
        "**Заказчик:** ОАО «АСБ Беларусбанк»  ",
        "**Исполнитель:** ООО «ГС Ритейл»  ",
        f"**Дата формирования:** {day.isoformat()}  ",
        f"**Стенд:** {stand}  ",
        f"**Источник результатов:** `{source}` (наборы SUF-T / CHAT-T / ASS-T / DOC-T / INT-T, VII.2)  ",
        "",
        "Документ является формальным приложением к приёмке по критериям ТЗ "
        "(идентификаторы `*-T-*`). Статусы переносятся из матрицы приёмки без изменения смысла.",
        "",
        "## 1. Сводка результатов (pass / fail)",
        "",
        "| Статус | Кол-во | Доля |",
        "|---|---:|---:|",
    ]

    total = summary["total"] or 1
    for status in STATUS_ORDER:
        count = counts[status]
        pct = 100.0 * count / total
        lines.append(
            f"| {status} ({STATUS_LABELS[status]}) | {count} | {pct:.1f}% |"
        )
    lines.extend(
        [
            f"| **Всего** | **{summary['total']}** | **100%** |",
            "",
            f"**Итог:** `{verdict_code}` — **{verdict_label}**",
            "",
            "## 2. Сводка по модулям",
            "",
            "| Модуль | pass | fail | pending | skip | всего |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )

    for module in summary["modules"]:
        mod = summary["by_module"][module]
        module_total = sum(mod.values())
        lines.append(
            "| {title} | {pass_} | {fail} | {pending} | {skip} | {total} |".format(
                title=_module_title(module),
                pass_=mod.get("pass", 0),
                fail=mod.get("fail", 0),
                pending=mod.get("pending", 0),
                skip=mod.get("skip", 0),
                total=module_total,
            )
        )

    lines.extend(["", "## 3. Результаты по сценариям", ""])

    for module in summary["modules"]:
        module_cases = [case for case in cases if case["module"] == module]
        lines.extend(
            [
                f"### {_module_title(module)}",
                "",
                "| id | status |",
                "|---|---|",
            ]
        )
        for case in module_cases:
            lines.append(f"| {case['id']} | {case['status']} |")
        lines.append("")

    lines.extend(
        [
            "## 4. Заключение",
            "",
            f"По состоянию на **{day.isoformat()}** по матрице приёмки "
            f"(`{source}`): **pass={counts['pass']}**, **fail={counts['fail']}**, "
            f"**pending={counts['pending']}**, **skip={counts['skip']}** "
            f"(всего {summary['total']}).",
            "",
            f"**Решение комиссии (черновик):** {verdict_label}.",
            "",
            "Замечания / особые мнения сторон:",
            "",
            "> _Заполнить при подписании._",
            "",
            "________________________________________________________________",
            "",
            "________________________________________________________________",
            "",
            "## 5. Подписи сторон",
            "",
            "### 5.1. Заказчик — ОАО «АСБ Беларусбанк»",
            "",
            "| Роль | ФИО | Должность | Подпись | Дата |",
            "|---|---|---|---|---|",
            "| Представитель заказчика | ________________ | ________________ | ________________ | __________ |",
            "| Член комиссии | ________________ | ________________ | ________________ | __________ |",
            "",
            "### 5.2. Исполнитель — ООО «ГС Ритейл»",
            "",
            "| Роль | ФИО | Должность | Подпись | Дата |",
            "|---|---|---|---|---|",
            "| Представитель исполнителя | ________________ | ________________ | ________________ | __________ |",
            "| Член комиссии | ________________ | ________________ | ________________ | __________ |",
            "",
            "---",
            "",
            "_Шаблон сформирован скриптом `tests/acceptance/generate_protocol.py`. "
            "Перегенерируйте после прогона acceptance (обновления `matrix.json`)._",
            "",
        ]
    )
    return "\n".join(lines)


def generate_protocol(
    matrix_path: Path = DEFAULT_MATRIX,
    output_path: Path = DEFAULT_OUTPUT,
    *,
    generated_on: date | None = None,
    stand: str = "тест / приёмочный стенд AI Hub",
) -> dict[str, Any]:
    """Read matrix.json and write protocol.md. Returns summary metadata."""
    cases = load_matrix(matrix_path)
    summary = summarize(cases)
    verdict_code, verdict_label = verdict(summary)
    markdown = render_protocol(
        cases,
        generated_on=generated_on,
        matrix_path=matrix_path,
        stand=stand,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return {
        "cases": len(cases),
        "output": str(output_path),
        "verdict": verdict_code,
        "verdict_label": verdict_label,
        "summary": summary["by_status"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate acceptance protocol.md from matrix.json "
            "(customer signature template)."
        ),
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX,
        help="Path to matrix.json (default: tests/acceptance/matrix.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to protocol.md (default: tests/acceptance/protocol.md)",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Protocol date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--stand",
        default="тест / приёмочный стенд AI Hub",
        help="Stand / environment label in the protocol header",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_protocol(
        args.matrix,
        args.output,
        generated_on=args.date,
        stand=args.stand,
    )
    print(
        "Wrote {output} ({cases} cases, verdict={verdict}).".format(**result)
    )


if __name__ == "__main__":
    main()
