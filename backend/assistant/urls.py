from django.urls import path

from assistant.views import (
    assistant_attachment_extract,
    assistant_attachment_ocr,
    assistant_chat,
    assistant_content_from_prompt,
    assistant_doc_template_generate,
    assistant_doc_templates,
    assistant_rpa_launch,
    assistant_rpa_scenarios,
    assistant_sandbox_snippet,
    assistant_sql_access,
    assistant_translate,
    assistant_knowledge_bases,
    assistant_models,
    assistant_openapi,
    assistant_skill_detail,
    assistant_skills,
    assistant_report_detail,
    assistant_reports_analytics,
    assistant_reports_catalog,
    assistant_reports_export,
    assistant_source_download,
)

urlpatterns = [
    path("chat", assistant_chat, name="assistant_chat"),
    path(
        "attachments/extract",
        assistant_attachment_extract,
        name="assistant_attachment_extract",
    ),
    path(
        "attachments/ocr",
        assistant_attachment_ocr,
        name="assistant_attachment_ocr",
    ),
    path(
        "sources/download",
        assistant_source_download,
        name="assistant_source_download",
    ),
    path("models/", assistant_models, name="assistant_models"),
    path("kbs/", assistant_knowledge_bases, name="assistant_knowledge_bases"),
    path("skills/", assistant_skills, name="assistant_user_skills"),
    path(
        "skills/<int:skill_id>/",
        assistant_skill_detail,
        name="assistant_user_skill_detail",
    ),
    path(
        "doc-templates/",
        assistant_doc_templates,
        name="assistant_doc_templates",
    ),
    path("rpa/scenarios/", assistant_rpa_scenarios, name="assistant_rpa_scenarios"),
    path("sandbox/", assistant_sandbox_snippet, name="assistant_sandbox_snippet"),
    path("sql/access/", assistant_sql_access, name="assistant_sql_access"),
    path("translate/", assistant_translate, name="assistant_translate"),
    path("rpa/launch/", assistant_rpa_launch, name="assistant_rpa_launch"),
    path(
        "doc-templates/<int:template_id>/generate/",
        assistant_doc_template_generate,
        name="assistant_doc_template_generate",
    ),
    path(
        "content/from-prompt/",
        assistant_content_from_prompt,
        name="assistant_content_from_prompt",
    ),
    path("openapi.json", assistant_openapi, name="assistant_openapi"),
    path("reports/", assistant_reports_catalog, name="assistant_reports_catalog"),
    path(
        "reports/analytics/",
        assistant_reports_analytics,
        name="assistant_reports_analytics",
    ),
    path(
        "reports/export/",
        assistant_reports_export,
        name="assistant_reports_export",
    ),
    path(
        "reports/<str:report_id>/",
        assistant_report_detail,
        name="assistant_report_detail",
    ),
]
