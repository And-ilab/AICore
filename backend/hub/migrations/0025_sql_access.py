from django.db import migrations, models


SEED = (
    {
        "name": "Карты клиентов",
        "object_name": "cards",
        "description": "Витрина карт. В запросе можно только читать.",
    },
    {
        "name": "Вклады",
        "object_name": "deposits",
        "description": "Витрина вкладов. В запросе можно только читать.",
    },
    {
        "name": "Заявки сотрудников",
        "object_name": "staff_requests",
        "description": "Витрина служебных заявок. В запросе можно только читать.",
    },
)


def seed(apps, schema_editor):
    Access = apps.get_model("hub", "AssistantSqlAccess")
    for row in SEED:
        Access.objects.get_or_create(
            object_name=row["object_name"],
            defaults={**row, "active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0024_rpa_whitelist"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantSqlAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("object_name", models.CharField(max_length=80, unique=True)),
                ("description", models.TextField(blank=True)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("updated_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
