from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0020_assistant_skill"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="source",
            field=models.CharField(
                choices=[("manual", "Ручная загрузка"), ("website", "Сайт")],
                db_index=True,
                default="manual",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="start_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="crawl_depth",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="max_pages",
            field=models.PositiveIntegerField(default=200),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="ignore_robots",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="allowed_hosts",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="AssistantWebsitePage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("url", models.URLField(max_length=1000)),
                ("title", models.CharField(blank=True, max_length=500)),
                ("extracted_text", models.TextField(blank=True)),
                ("http_status", models.PositiveSmallIntegerField(default=0)),
                ("content_type", models.CharField(blank=True, max_length=128)),
                ("size_bytes", models.PositiveIntegerField(default=0)),
                ("article_id", models.BigIntegerField(unique=True)),
                ("checksum", models.CharField(blank=True, max_length=80)),
                ("skipped_reason", models.CharField(blank=True, max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "knowledge_base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="website_pages",
                        to="hub.assistantknowledgebase",
                    ),
                ),
            ],
            options={"ordering": ("url",)},
        ),
        migrations.AddConstraint(
            model_name="assistantwebsitepage",
            constraint=models.UniqueConstraint(
                fields=("knowledge_base", "url"),
                name="asst_website_page_url_uniq",
            ),
        ),
        migrations.CreateModel(
            name="AssistantWebsiteCrawlJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("crawling", "Crawling"),
                            ("indexing", "Indexing"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("status_message", models.CharField(blank=True, max_length=500)),
                ("pages_ok", models.PositiveIntegerField(default=0)),
                ("pages_4xx", models.PositiveIntegerField(default=0)),
                ("pages_5xx", models.PositiveIntegerField(default=0)),
                ("pages_skipped", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "knowledge_base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crawl_jobs",
                        to="hub.assistantknowledgebase",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
