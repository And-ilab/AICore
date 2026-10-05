from django.db import migrations, models


def set_default_max_hints(apps, schema_editor):
    SuflerPolicy = apps.get_model("hub", "SuflerPolicy")
    SuflerPolicy.objects.filter(pk=1).update(max_hints=1)


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0010_sufler_policy"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="suflerpolicy",
            name="chat_min_relevance_percent",
        ),
        migrations.AlterField(
            model_name="suflerpolicy",
            name="max_hints",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.RunPython(set_default_max_hints, migrations.RunPython.noop),
    ]
