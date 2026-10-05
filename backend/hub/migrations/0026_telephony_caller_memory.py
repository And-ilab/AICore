from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0021_assistant_website_crawl"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelephonyCallerMemory",
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
                ("phone", models.CharField(max_length=32, unique=True)),
                ("question", models.CharField(max_length=240)),
                ("asked_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-asked_at",),
            },
        ),
    ]
