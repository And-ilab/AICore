import importlib

from django.db import migrations


def repair_feedback_source_fields(apps, schema_editor):
    migration = importlib.import_module(
        "online_chat.migrations.0027_sufler_feedback_source"
    )
    migration.add_feedback_source_fields(apps, schema_editor)


class Migration(migrations.Migration):
    """Repair DBs where 0027 added call_id but SQLite table rebuild dropped source."""

    dependencies = [
        ("online_chat", "0029_message_source_base"),
    ]

    operations = [
        migrations.RunPython(
            repair_feedback_source_fields,
            migrations.RunPython.noop,
        ),
    ]
