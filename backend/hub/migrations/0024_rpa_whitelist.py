from django.db import migrations, models
import django.db.models.deletion


SEED = (
    {
        "name": "Заявка на карту",
        "code": "card-request",
        "description": "Робот открывает форму заявки на карту в системе банка и заполняет её.",
    },
    {
        "name": "Блокировка карты",
        "code": "card-block",
        "description": "Робот блокирует карту в системе банка.",
    },
    {
        "name": "Служебная заявка",
        "code": "staff-request",
        "description": "Робот создаёт внутреннюю заявку в системе банка.",
    },
)


def seed(apps, schema_editor):
    Scenario = apps.get_model("hub", "AssistantRpaScenario")
    for row in SEED:
        Scenario.objects.get_or_create(code=row["code"], defaults={**row, "active": True})


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0023_slide_template_is_outline"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantRpaScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(max_length=64, unique=True)),
                ("description", models.TextField(blank=True)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("updated_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="AssistantRpaRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("confirmed", "Подтверждено")], default="confirmed", max_length=16)),
                ("detail", models.CharField(blank=True, max_length=500)),
                ("requested_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "scenario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="hub.assistantrpascenario",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
