"""Internal KC test-dialog pipeline (II.3.5.5 / II-KC, SUF-T-06)."""

from __future__ import annotations

from typing import Any

from orchestrator.sufler import SuflerOrchestratorError, suggest

SCENARIO_SOURCES: dict[str, dict[str, str]] = {
    "CC-SCR-008": {
        "title": "Вклады · Стройсбережения",
        "scenario": "CC-SCR-008",
        "permalink": "https://suz.local/articles/deposit-stroysberezheniya",
        "etalon": "Срок вклада «Стройсбережения»",
    },
    "CC-SCR-003": {
        "title": "Переводы · лимиты",
        "scenario": "CC-SCR-003",
        "permalink": "https://suz.local/articles/transfers-limits",
        "etalon": "Лимиты перевода между счетами",
    },
    "CC-SCR-001": {
        "title": "Карты · оформление",
        "scenario": "CC-SCR-001",
        "permalink": "https://suz.local/articles/card-issue",
        "etalon": "Как оформить банковскую карту",
    },
}


def _relevance_tone(percent: int) -> str:
    if percent >= 85:
        return "success"
    if percent >= 70:
        return "warning"
    return "danger"


def _stub_answer(text: str, scenario_id: str) -> dict[str, Any]:
    meta = SCENARIO_SOURCES.get(scenario_id, SCENARIO_SOURCES["CC-SCR-008"])
    lowered = text.casefold()
    if "досроч" in lowered or "закрыть" in lowered:
        percent = 76
        answer = (
            "При досрочном расторжении проценты пересчитываются по ставке "
            "вклада «до востребования». Полное сохранение процентов не предусмотрено."
        )
    elif "документ" in lowered:
        percent = 89
        answer = (
            "Для открытия вклада нужны паспорт и заявление. "
            "Дополнительный пакет документов зависит от продукта."
        )
    elif "вклад" in lowered or "стройсбереж" in lowered:
        percent = 91
        answer = (
            "Срок вклада определяется договором; минимальный срок — 12 месяцев. "
            "Конкретный срок указывается при оформлении."
        )
    else:
        percent = 68
        answer = (
            f"По сценарию {scenario_id}: ответ сформирован в test-dialog harness. "
            "Уточните формулировку ближе к эталону QU для повышения релевантности."
        )
    return {
        "query": text,
        "scenario_id": scenario_id,
        "prompt_profile": "sufler_cc",
        "llm_text": answer,
        "relevance_percent": percent,
        "relevance_tone": _relevance_tone(percent),
        "sources": [
            {
                "title": meta["title"],
                "scenario": meta["scenario"],
                "permalink": meta["permalink"],
            }
        ],
        "etalon": meta["etalon"],
        "stub": True,
        "request_id": "stub-test-dialog",
        "latency_ms": {"total": 12.0},
    }


def run_test_prompt(
    text: str,
    *,
    scenario_id: str = "CC-SCR-008",
    use_pipeline: bool = True,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Answer a test prompt with relevance for the internal KC dialog."""
    normalized = text.strip() if isinstance(text, str) else ""
    if not normalized:
        raise SuflerOrchestratorError("text must be a non-empty string")
    scenario = (scenario_id or "CC-SCR-008").strip().upper()
    if scenario not in SCENARIO_SOURCES:
        raise SuflerOrchestratorError(
            "scenario_id must be one of: " + ", ".join(sorted(SCENARIO_SOURCES))
        )

    if not use_pipeline:
        return _stub_answer(normalized, scenario)

    try:
        result = suggest(normalized, limit=3, request_id=request_id)
    except Exception:
        return _stub_answer(normalized, scenario)

    meta = SCENARIO_SOURCES[scenario]
    hints = result.get("hints") or []
    if not hints:
        stub = _stub_answer(normalized, scenario)
        stub["stub"] = False
        stub["blocked_reason"] = result.get("blocked_reason")
        stub["request_id"] = result.get("request_id", stub["request_id"])
        stub["latency_ms"] = result.get("latency_ms", stub["latency_ms"])
        return stub

    top = hints[0]
    percent = int(top.get("relevance_percent") or 0)
    citations = top.get("citations") or []
    sources = []
    for citation in citations[:3]:
        sources.append(
            {
                "title": citation.get("title") or meta["title"],
                "scenario": scenario,
                "permalink": citation.get("permalink") or meta["permalink"],
            }
        )
    if not sources:
        sources = [
            {
                "title": meta["title"],
                "scenario": meta["scenario"],
                "permalink": meta["permalink"],
            }
        ]

    return {
        "query": normalized,
        "scenario_id": scenario,
        "prompt_profile": "sufler_cc",
        "llm_text": top.get("text") or "",
        "relevance_percent": percent,
        "relevance_tone": _relevance_tone(percent),
        "sources": sources,
        "etalon": meta["etalon"],
        "stub": False,
        "request_id": result.get("request_id"),
        "latency_ms": result.get("latency_ms", {}),
        "blocked_reason": result.get("blocked_reason"),
    }
