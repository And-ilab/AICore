from django.urls import path

from ocr.views import (
    ocr_doc_types,
    ocr_export,
    ocr_job_approve,
    ocr_job_detail,
    ocr_job_export,
    ocr_job_original,
    ocr_job_result,
    ocr_jobs_list,
    ocr_my_template_detail,
    ocr_my_templates,
    ocr_template_detail,
    ocr_template_sample,
    ocr_templates,
    ocr_upload,
    ocr_validate,
)

urlpatterns = [
    path("documents/", ocr_upload, name="ocr_upload"),
    path("doc-types/", ocr_doc_types, name="ocr_doc_types"),
    path("templates/", ocr_templates, name="ocr_templates"),
    path(
        "templates/<slug:doc_type>/",
        ocr_template_detail,
        name="ocr_template_detail",
    ),
    path(
        "templates/<slug:doc_type>/samples/",
        ocr_template_sample,
        name="ocr_template_sample",
    ),
    path("validate/", ocr_validate, name="ocr_validate"),
    path("export/", ocr_export, name="ocr_export"),
    path("my-templates/", ocr_my_templates, name="ocr_my_templates"),
    path(
        "my-templates/<int:template_id>/",
        ocr_my_template_detail,
        name="ocr_my_template_detail",
    ),
    path("jobs/", ocr_jobs_list, name="ocr_jobs_list"),
    path("jobs/<str:job_id>/", ocr_job_detail, name="ocr_job_detail"),
    path(
        "jobs/<str:job_id>/result/",
        ocr_job_result,
        name="ocr_job_result",
    ),
    path(
        "jobs/<str:job_id>/original/",
        ocr_job_original,
        name="ocr_job_original",
    ),
    path(
        "jobs/<str:job_id>/approve/",
        ocr_job_approve,
        name="ocr_job_approve",
    ),
    path(
        "jobs/<str:job_id>/export/",
        ocr_job_export,
        name="ocr_job_export",
    ),
]
