from django.apps import AppConfig


class ApiDocsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api_docs"
    verbose_name = "API OpenAPI / Postman docs"
