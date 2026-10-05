from django.db import migrations, models
import django.db.models.deletion
import uuid


def _table_exists(schema_editor, table: str) -> bool:
    return table in schema_editor.connection.introspection.table_names()


def create_presence_log_if_missing(apps, schema_editor):
    table = "online_chat_operatorpresencelog"
    if _table_exists(schema_editor, table):
        return

    operator_profile = apps.get_model("online_chat", "OperatorProfile")

    class OperatorPresenceLog(models.Model):
        id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
        operator = models.ForeignKey(
            operator_profile,
            on_delete=django.db.models.deletion.CASCADE,
            related_name="presence_logs",
        )
        presence = models.CharField(max_length=16, db_index=True)
        started_at = models.DateTimeField(db_index=True)
        ended_at = models.DateTimeField(null=True, blank=True, db_index=True)

        class Meta:
            # Avoid clashing with online_chat.models.OperatorPresenceLog during migrate.
            app_label = "_migration_online_chat_0028"
            db_table = table
            ordering = ("started_at",)
            indexes = (
                models.Index(
                    fields=["operator", "started_at"],
                    name="oc_oppres_started_idx",
                ),
                models.Index(
                    fields=["operator", "ended_at"],
                    name="oc_oppres_ended_idx",
                ),
            )

    schema_editor.create_model(OperatorPresenceLog)


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0027_sufler_feedback_source"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OperatorPresenceLog",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("presence", models.CharField(db_index=True, max_length=16)),
                        ("started_at", models.DateTimeField(db_index=True)),
                        (
                            "ended_at",
                            models.DateTimeField(blank=True, db_index=True, null=True),
                        ),
                        (
                            "operator",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="presence_logs",
                                to="online_chat.operatorprofile",
                            ),
                        ),
                    ],
                    options={
                        "ordering": ("started_at",),
                    },
                ),
                migrations.AddIndex(
                    model_name="operatorpresencelog",
                    index=models.Index(
                        fields=["operator", "started_at"],
                        name="oc_oppres_started_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="operatorpresencelog",
                    index=models.Index(
                        fields=["operator", "ended_at"],
                        name="oc_oppres_ended_idx",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    create_presence_log_if_missing,
                    migrations.RunPython.noop,
                ),
            ],
        ),
    ]
