"""Layered, reproducible evaluation for the contact-center sufler pipeline."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DEFAULT_DATASET_PATH = REPOSITORY_ROOT / "benchmarks" / "datasets" / "sufler_eval_100.json"
LAYERS = ("classification", "scenario", "retrieval", "full_suggest")

for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


class EvaluationInputError(ValueError):
    """Raised when the evaluation dataset or CLI options are invalid."""


class EvaluationAdapters(Protocol):
    """Runtime boundary, injectable so unit tests never need DB or network."""

    def classify(self, text: str) -> str | None: ...

    def scenario(self, case: Mapping[str, Any]) -> Mapping[str, Any] | None: ...

    def retrieve(self, text: str) -> Mapping[str, Any]: ...

    def suggest(self, case: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()


@dataclass
class DefaultAdapters:
    """Adapters for the real local pipeline; stub gateway is the safe default."""

    gateway_mode: str = "stub"
    session_prefix: str = "sufler-eval"

    def preload(self, texts: Sequence[str]) -> None:
        _setup_django()
        from core.embeddings import preload_query_embeddings

        preload_query_embeddings(texts)

    def classify(self, text: str) -> str | None:
        _setup_django()
        from orchestrator.scenario_engine import classify_turn

        return classify_turn(text)

    def scenario(self, case: Mapping[str, Any]) -> Mapping[str, Any] | None:
        _setup_django()
        from orchestrator.scenario_engine import advance_scenario, clear_scenario_session

        case_input = case["input"]
        session_key = f"{self.session_prefix}:{case['id']}"
        clear_scenario_session(session_key)
        progress = None
        for turn in [*case_input.get("prior_turns", []), case_input["text"]]:
            progress = advance_scenario(str(turn), session_key=session_key)
        if progress is None:
            return None
        result = progress.as_dict()
        result["title"] = progress.title
        result["node_type"] = progress.node_type
        return result

    def retrieve(self, text: str) -> Mapping[str, Any]:
        _setup_django()
        from qu.service import preview_query

        return preview_query(text, limit=5, snippet_chars=2000)

    def suggest(self, case: Mapping[str, Any]) -> Mapping[str, Any]:
        _setup_django()
        from core.model_gateway import ModelGateway
        from orchestrator.sufler import suggest

        case_input = case["input"]
        prior_turns = [str(item) for item in case_input.get("prior_turns", [])]
        gateway = ModelGateway.from_registry(mode=self.gateway_mode)
        session_id = f"{self.session_prefix}:{case['id']}:full"
        from orchestrator.scenario_engine import clear_scenario_session

        clear_scenario_session(session_id)
        response: Mapping[str, Any] = {}
        for index, turn in enumerate([*prior_turns, str(case_input["text"])]):
            response = suggest(
                turn,
                gateway=gateway,
                dialog_context="\n".join(prior_turns[:index]),
                session_id=session_id,
            )
        return response


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvaluationInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(f"Invalid dataset JSON: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("samples"), list):
        raise EvaluationInputError("Dataset must be an object with a samples array")
    return payload


def _percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _routing_from_suggest(response: Mapping[str, Any]) -> str:
    blocked = response.get("blocked_reason")
    if blocked:
        return "no_hint" if blocked == "no_hint_needed" else f"blocked:{blocked}"
    if response.get("scenario"):
        return "scenario"
    if response.get("hints"):
        return "knowledge_base"
    return "no_match"


def _flatten_citations(hints: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(citation)
        for hint in hints
        for citation in hint.get("citations", [])
        if isinstance(citation, Mapping)
    ]


def _expected_route(case: Mapping[str, Any], layer: str) -> str | None:
    expected = case["expected"]
    if layer == "classification":
        return "no_hint" if expected.get("classification") else "needs_hint"
    if layer == "scenario":
        return "scenario" if expected.get("scenario_code") else (
            "no_hint" if expected.get("route") == "no_hint" else "no_scenario"
        )
    return expected.get("route")


def _evaluate_case(
    case: Mapping[str, Any],
    layer: str,
    adapters: EvaluationAdapters,
    clock: Callable[[], float],
) -> dict[str, Any]:
    text = str(case["input"]["text"])
    started = clock()
    actual: dict[str, Any] = {
        "routing": None,
        "classification": None,
        "scenario": None,
        "retrieval": {"documents": []},
        "hints": [],
        "citations": [],
        "blocked_reason": None,
        "error": None,
    }

    try:
        if layer == "classification":
            intent = adapters.classify(text)
            actual["classification"] = intent
            actual["routing"] = "no_hint" if intent else "needs_hint"
        elif layer == "scenario":
            scenario = adapters.scenario(case)
            actual["scenario"] = dict(scenario) if scenario else None
            if scenario:
                actual["routing"] = "scenario"
            elif case["expected"].get("route") == "no_hint":
                actual["routing"] = "no_hint"
            else:
                actual["routing"] = "no_scenario"
        elif layer == "retrieval":
            retrieval = adapters.retrieve(text)
            documents = [
                dict(item)
                for item in retrieval.get("documents", [])
                if isinstance(item, Mapping)
            ]
            actual["retrieval"] = {"documents": documents}
            actual["routing"] = "knowledge_base" if documents else "no_match"
            actual["citations"] = [
                {
                    "article_id": item.get("article_id"),
                    "title": item.get("title"),
                    "permalink": item.get("permalink"),
                }
                for item in documents
            ]
        elif layer == "full_suggest":
            response = adapters.suggest(case)
            hints = [
                dict(item)
                for item in response.get("hints", [])
                if isinstance(item, Mapping)
            ]
            actual.update(
                {
                    "routing": _routing_from_suggest(response),
                    "scenario": response.get("scenario"),
                    "hints": hints,
                    "citations": _flatten_citations(hints),
                    "blocked_reason": response.get("blocked_reason"),
                    "pipeline_latency_ms": response.get("latency_ms", {}),
                    "request_id": response.get("request_id"),
                }
            )
        else:
            raise EvaluationInputError(f"Unsupported layer: {layer}")
    except Exception as exc:  # noqa: BLE001 - record per-case failures and continue
        actual["routing"] = "error"
        actual["error"] = f"{type(exc).__name__}: {exc}"

    latency_ms = round((clock() - started) * 1000, 3)
    expected = dict(case["expected"])
    checks: dict[str, bool] = {}
    expected_route = _expected_route(case, layer)
    if expected_route is not None:
        checks["routing"] = actual["routing"] == expected_route
    if actual["error"]:
        checks["execution"] = False
    if layer == "classification" and "classification" in expected:
        checks["classification"] = actual["classification"] == expected["classification"]
    if layer == "scenario" and expected.get("scenario_code"):
        scenario = actual.get("scenario") or {}
        checks["scenario_code"] = scenario.get("code") == expected["scenario_code"]
        if expected.get("node_id"):
            checks["node_id"] = scenario.get("node_id") == expected["node_id"]
    if layer in {"retrieval", "full_suggest"} and expected.get("source_titles"):
        titles = {
            str(item.get("title") or "").casefold()
            for item in actual["citations"]
        }
        checks["source_title"] = any(
            any(wanted.casefold() in title for title in titles)
            for wanted in expected["source_titles"]
        )
    if layer == "full_suggest" and expected.get("required_concepts") and actual["hints"]:
        answer = " ".join(str(item.get("text") or "") for item in actual["hints"]).casefold()
        checks["required_concepts"] = all(
            concept.casefold() in answer for concept in expected["required_concepts"]
        )

    return {
        "id": case["id"],
        "version": case["version"],
        "bucket": case["bucket"],
        "case_type": case["case_type"],
        "layer": layer,
        "input": dict(case["input"]),
        "expected": expected,
        "actual": actual,
        "checks": checks,
        "passed": all(checks.values()) if checks else True,
        "latency_ms": latency_ms,
    }


def _case_applies(case: Mapping[str, Any], layer: str) -> bool:
    if layer == "classification":
        return "classification" in case["expected"]
    if layer == "scenario":
        return case["bucket"] == "scenario"
    if layer == "retrieval":
        return case["bucket"] == "kb"
    return True


def run(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    layers: Sequence[str] = LAYERS,
    adapters: EvaluationAdapters | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    invalid_layers = set(layers) - set(LAYERS)
    if invalid_layers:
        raise EvaluationInputError(f"Unknown layers: {sorted(invalid_layers)}")
    runtime = adapters or DefaultAdapters()
    if any(layer in {"retrieval", "full_suggest"} for layer in layers):
        preload = getattr(runtime, "preload", None)
        if callable(preload):
            preload(
                [
                    str(case["input"]["text"])
                    for case in dataset["samples"]
                    if case["bucket"] == "kb"
                ]
            )
    results = [
        _evaluate_case(case, layer, runtime, clock)
        for layer in layers
        for case in dataset["samples"]
        if _case_applies(case, layer)
    ]
    generated_at = datetime.now(timezone.utc)
    layer_metrics: dict[str, Any] = {}
    for layer in layers:
        selected = [item for item in results if item["layer"] == layer]
        latencies = [item["latency_ms"] for item in selected]
        passed = sum(item["passed"] for item in selected)
        layer_metrics[layer] = {
            "cases": len(selected),
            "passed": passed,
            "failed": len(selected) - passed,
            "pass_rate_percent": round(passed / len(selected) * 100, 2) if selected else 0.0,
            "latency_ms": {
                "p50": round(_percentile(latencies, 50), 3),
                "p95": round(_percentile(latencies, 95), 3),
            },
        }
    return {
        "schema_version": "1.0",
        "report_id": f"sufler-eval-{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}",
        "suite": "sufler_eval",
        "generated_at": generated_at.isoformat(),
        "dataset": {
            "id": dataset.get("id"),
            "version": dataset.get("version"),
            "path": str(dataset_path),
            "case_count": len(dataset["samples"]),
        },
        "layers": list(layers),
        "metrics": {"layers": layer_metrics},
        "results": results,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Sufler evaluation: {report['report_id']}",
        "",
        f"- Dataset: `{report['dataset']['id']}` v{report['dataset']['version']}",
        f"- Cases: {report['dataset']['case_count']}",
        f"- Generated: {report['generated_at']}",
        "",
        "## Layer summary",
        "",
        "| Layer | Cases | Passed | Failed | Pass rate | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for layer, metric in report["metrics"]["layers"].items():
        lines.append(
            f"| {layer} | {metric['cases']} | {metric['passed']} | "
            f"{metric['failed']} | {metric['pass_rate_percent']:.2f}% | "
            f"{metric['latency_ms']['p50']:.3f} | {metric['latency_ms']['p95']:.3f} |"
        )
    failures = [item for item in report["results"] if not item["passed"]]
    lines.extend(["", f"## Failures ({len(failures)})", ""])
    if not failures:
        lines.append("None.")
    else:
        for item in failures:
            failed_checks = [key for key, passed in item["checks"].items() if not passed]
            lines.append(
                f"- `{item['id']}` / `{item['layer']}`: "
                f"{', '.join(failed_checks) or 'unspecified mismatch'}"
            )
    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    stem = str(report["report_id"])
    json_path = output / f"{stem}.json"
    markdown_path = output / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the layered 100-case sufler evaluation.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--layers",
        nargs="+",
        choices=LAYERS,
        default=list(LAYERS),
    )
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument(
        "--gateway-mode",
        choices=("stub", "openai"),
        default="stub",
        help="Full-suggest gateway. Stub is the network-free default.",
    )
    parser.add_argument(
        "--allow-live-llm",
        action="store_true",
        help="Required together with --gateway-mode openai.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gateway_mode == "openai" and not args.allow_live_llm:
        raise EvaluationInputError(
            "--gateway-mode openai requires explicit --allow-live-llm"
        )
    report = run(
        dataset_path=args.dataset,
        layers=args.layers,
        adapters=DefaultAdapters(gateway_mode=args.gateway_mode),
    )
    json_path, markdown_path = write_reports(report, args.output)
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
