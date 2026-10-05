from django.db import migrations, models


def _existing_columns(schema_editor, table: str) -> set[str]:
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(
            cursor,
            table,
        )
    return {column.name for column in description}


def add_source_base_message_id(apps, schema_editor):
    model = apps.get_model("online_chat", "DialogMessage")
    table = model._meta.db_table
    existing = _existing_columns(schema_editor, table)
    if "source_base_message_id" in existing:
        return
    field = models.UUIDField(blank=True, db_index=True, null=True)
    field.set_attributes_from_name("source_base_message_id")
    schema_editor.add_field(model, field)


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0028_operator_presence_log"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="dialogmessage",
                    name="source_base_message_id",
                    field=models.UUIDField(blank=True, db_index=True, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    add_source_base_message_id,
                    migrations.RunPython.noop,
                ),
            ],
        ),
    ]
