"""Verify TEST AI inference tier: deployment profile=test, LLM stub, ASR, suggest."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.model_gateway import ModelGateway
from core.model_registry import ModelRegistry
from ingest.models import CCProductionChunk
from ingest.pipeline import deterministic_embedding
from orchestrator.sufler import suggest


class Command(BaseCommand):
    help = (
        "Verify AI inference tier: ModelRegistry deployment profile, "
        "LLM gateway, ASR health, end-to-end sufler suggest smoke."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            default=None,
            help="Deployment profile name (default: AI_INFERENCE_PROFILE or test)",
        )
        parser.add_argument(
            "--skip-asr",
            action="store_true",
            help="Skip ASR HTTP health (local without compose asr service)",
        )
        parser.add_argument(
            "--skip-suggest",
            action="store_true",
            help="Skip end-to-end suggest smoke",
        )

    def handle(self, *args, **options):
        profile_name = (
            options["profile"]
            or getattr(settings, "AI_INFERENCE_PROFILE", "")
            or "test"
        )
        registry_path = getattr(settings, "MODEL_REGISTRY_PATH", None)
        if registry_path:
            registry = ModelRegistry.load(registry_path)
        else:
            registry = ModelRegistry.load()
        try:
            deploy = registry.get_deployment_profile(profile_name)
        except KeyError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"deployment profile: {deploy.name} "
                f"(status={deploy.status}, gpu_required={deploy.gpu_required})"
            )
        )
        if deploy.gpu_required:
            self.stdout.write(
                self.style.WARNING(
                    "GPU required by profile — ensure NVIDIA device is allocated "
                    "on the TEST VM / compose device_requests"
                )
            )
        else:
            self.stdout.write("GPU: not required for this profile (approved_dev stubs)")

        asr_slot = registry.get_slot(deploy.asr_slot)
        self.stdout.write(
            f"ASR slot: {asr_slot.name} model={asr_slot.dev_model} "
            f"mode={deploy.asr_mode}"
        )

        mode_override = (
            os.getenv("MODEL_GATEWAY_MODE", "").strip()
            or deploy.llm_gateway_mode
        )
        gateway = ModelGateway(registry, mode=mode_override)
        for llm_profile in deploy.llm_profiles:
            configured = gateway.get_profile(llm_profile)
            response = gateway.chat(
                llm_profile,
                [{"role": "user", "content": "ping inference tier"}],
            )
            content = (
                response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not content:
                raise CommandError(f"LLM profile {llm_profile} returned empty content")
            self.stdout.write(
                self.style.SUCCESS(
                    f"LLM {llm_profile}: ok "
                    f"(mode={configured.gateway_mode}, model={configured.model})"
                )
            )

        if not options["skip_asr"]:
            self._check_asr()
        else:
            self.stdout.write(self.style.WARNING("ASR: skipped (--skip-asr)"))

        if not options["skip_suggest"]:
            self._suggest_smoke(gateway)
        else:
            self.stdout.write(self.style.WARNING("suggest: skipped"))

        self.stdout.write(self.style.SUCCESS("verify_inference_tier: OK"))

    def _check_asr(self) -> None:
        url = getattr(
            settings,
            "ASR_HEALTH_URL",
            os.getenv("ASR_HEALTH_URL", "http://asr:8764/health"),
        )
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CommandError(f"ASR health failed ({url}): {exc}") from exc
        if body.get("status") != "ok":
            raise CommandError(f"ASR unhealthy: {body}")
        self.stdout.write(
            self.style.SUCCESS(
                f"ASR: ok (mode={body.get('mode')}, profile={body.get('profile')})"
            )
        )

    def _suggest_smoke(self, gateway: ModelGateway) -> None:
        query = "как оформить банковскую карту"
        article_id = 91001
        CCProductionChunk.objects.filter(article_id=article_id).delete()
        try:
            CCProductionChunk.objects.create(
                article_id=article_id,
                version_id=1,
                chunk_index=0,
                title="Оформление карты (inference smoke)",
                content=query,
                permalink="https://suz.local/articles/91001",
                locale="ru",
                visibility_scope=["kc_operator"],
                checksum="sha256:inference-smoke",
                embedding_model="deterministic-dev",
                embedding=deterministic_embedding(query),
            )
            result = suggest(query, limit=3, gateway=gateway)
            if not result.get("hints"):
                raise CommandError(
                    f"suggest smoke returned no hints: {result.get('blocked_reason')}"
                )
            hint = result["hints"][0]["text"]
            hint_l = hint.lower()
            grounded = "карт" in hint_l or query.lower() in hint_l
            if (
                "суз" not in hint_l
                and "подсказка" not in hint
                and "уточните" not in hint_l
                and "ответ" not in hint_l
                and not grounded
            ):
                raise CommandError(f"unexpected stub hint text: {hint[:80]!r}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"suggest smoke: ok (hints={len(result['hints'])}, "
                    f"model={result.get('gateway_model')})"
                )
            )
        finally:
            CCProductionChunk.objects.filter(article_id=article_id).delete()
