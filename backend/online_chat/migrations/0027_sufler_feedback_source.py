from django.db import migrations, models


def _existing_columns(schema_editor, table: str) -> set[str]:
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(
            cursor,
            table,
        )
    return {column.name for column in description}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _add_varchar_column(schema_editor, table: str, column: str, *, max_length: int, default: str):
    qn = schema_editor.quote_name
    schema_editor.execute(
        f"ALTER TABLE {qn(table)} "
        f"ADD COLUMN {qn(column)} varchar({max_length}) NOT NULL "
        f"DEFAULT {_sql_literal(default)}"
    )


def add_feedback_source_fields(apps, schema_editor):
    """Add source/call_id only if missing.

    Feature-branch stands already applied these columns as
    online_chat.0014_sufler_feedback_source, which was renamed to 0027
    so it no longer collides with 0014_base_messages_bot_offline.

    Use ALTER TABLE instead of schema_editor.add_field so SQLite does not
    rebuild the table from the pre-migration model (which would drop a
    column added in the same RunPython step).
    """
    model = apps.get_model("online_chat", "SuflerHintFeedback")
    table = model._meta.db_table
    existing = _existing_columns(schema_editor, table)
    if "source" not in existing:
        _add_varchar_column(
            schema_editor,
            table,
            "source",
            max_length=32,
            default="chat",
        )
    if "call_id" not in existing:
        _add_varchar_column(
            schema_editor,
            table,
            "call_id",
            max_length=64,
            default="",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0026_dialog_client_ip"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="suflerhintfeedback",
                    name="source",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="chat",
                        max_length=32,
                    ),
                ),
                migrations.AddField(
                    model_name="suflerhintfeedback",
                    name="call_id",
                    field=models.CharField(blank=True, default="", max_length=64),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    add_feedback_source_fields,
                    migrations.RunPython.noop,
                ),
            ],
        ),
    ]
