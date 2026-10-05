from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_org_skills(apps, schema_editor):
    from hub.skill_store import ensure_org_skill_seed

    ensure_org_skill_seed()


def unseed_org_skills(apps, schema_editor):
    AssistantSkill = apps.get_model("hub", "AssistantSkill")
    AssistantSkill.objects.filter(
        scope="org",
        code__in=[
            "SKL-01",
            "SKL-02",
            "SKL-03",
            "SKL-04",
            "SKL-05",
            "SKL-06",
            "SKL-07",
            "SKL-08",
        ],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0019_text_slides_diagram_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantSkill",
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
                ("code", models.CharField(blank=True, default="", max_length=32)),
                (
                    "scope",
                    models.CharField(
                        choices=[("org", "Банк"), ("user", "Мои")],
                        db_index=True,
                        max_length=8,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("alias", models.CharField(max_length=64)),
                ("instruction", models.TextField()),
                ("needs_attachment", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "department_scope",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("updated_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_skills",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("scope", "code", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="assistantskill",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "org")),
                fields=("alias",),
                name="uniq_assistant_skill_org_alias",
            ),
        ),
        migrations.AddConstraint(
            model_name="assistantskill",
            constraint=models.UniqueConstraint(
                condition=models.Q(("scope", "user")),
                fields=("owner", "alias"),
                name="uniq_assistant_skill_user_alias",
            ),
        ),
        migrations.AddConstraint(
            model_name="assistantskill",
            constraint=models.UniqueConstraint(
                condition=~models.Q(code=""),
                fields=("code",),
                name="uniq_assistant_skill_code",
            ),
        ),
        migrations.RunPython(seed_org_skills, unseed_org_skills),
    ]
