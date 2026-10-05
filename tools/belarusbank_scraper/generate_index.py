"""Build INDEX.md with topic/subtopic article counts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scrape_belarusbank import SUBTOPIC_LABELS, TOPIC_LABELS


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "local" / "kb" / "belarusbank"
    articles = root / "articles"
    counts: Counter[tuple[str, str]] = Counter()
    for path in articles.rglob("*.txt"):
        parts = path.relative_to(articles).parts
        if len(parts) >= 2:
            counts[(parts[0], parts[1])] += 1

    lines = [
        "# Статьи belarusbank.by (локальный корпус для БЗ)",
        "",
        f"Каталог: `{articles}`",
        "",
        "| Тема | Подтема | Файлов |",
        "|------|---------|--------|",
    ]
    by_topic: Counter[str] = Counter()
    for (topic, sub), n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        by_topic[topic] += n
        t_label = TOPIC_LABELS.get(topic, topic)
        s_label = SUBTOPIC_LABELS.get(sub, sub)
        lines.append(f"| {t_label} (`{topic}`) | {s_label} (`{sub}`) | {n} |")

    lines.extend(["", "## Итого по темам", ""])
    for topic, n in by_topic.most_common():
        lines.append(f"- **{TOPIC_LABELS.get(topic, topic)}**: {n}")
    lines.append("")
    lines.append(f"**Всего файлов:** {sum(by_topic.values())}")

    (root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "topics.json").write_text(
        json.dumps(
            {
                "total": sum(by_topic.values()),
                "by_topic": dict(by_topic),
                "by_subtopic": {
                    f"{t}/{s}": n for (t, s), n in counts.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {root / 'INDEX.md'} total={sum(by_topic.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
