from django.urls import path

from orchestrator.views import (
    sufler_scenario_clear,
    sufler_scenario_enter,
    sufler_scenario_exit,
    sufler_scenario_resume,
    sufler_suggest,
    sufler_test_dialog,
    sufler_transcribe,
)

urlpatterns = [
    path("suggest", sufler_suggest, name="sufler_suggest"),
    path("test-dialog", sufler_test_dialog, name="sufler_test_dialog"),
    path("transcribe", sufler_transcribe, name="sufler_transcribe"),
    path("scenario/enter", sufler_scenario_enter, name="sufler_scenario_enter"),
    path("scenario/exit", sufler_scenario_exit, name="sufler_scenario_exit"),
    path("scenario/clear", sufler_scenario_clear, name="sufler_scenario_clear"),
    path("scenario/resume", sufler_scenario_resume, name="sufler_scenario_resume"),
]
