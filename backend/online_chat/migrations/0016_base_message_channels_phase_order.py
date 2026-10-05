from django.db import migrations, models


PHASE_BY_TYPE = {
    "welcome": "before_bot",
    "offline": "offline",
    "broadcast": "after_bot",
}


def populate_base_message_delivery(apps, schema_editor):
    BaseMessage = apps.get_model("online_chat", "BaseMessage")
    for index, message in enumerate(BaseMessage.objects.order_by("created_at"), start=1):
        if message.placement_id:
            channels = [f"widget:{message.placement_id}"]
        elif message.channel:
            channels = [message.channel]
        else:
            channels = []
        message.channels = channels
        message.send_phase = PHASE_BY_TYPE.get(message.message_type, "before_bot")
        message.sort_order = index * 10
        message.save(update_fields=["channels", "send_phase", "sort_order"])


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0015_service_level_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="basemessage",
            name="message_type",
            field=models.CharField(
                choices=[
                    ("welcome", "Приветствие"),
                    ("offline", "Вне графика"),
                    ("broadcast", "Оповещение"),
                ],
                db_index=True,
                default="welcome",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="basemessage",
            name="channels",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="basemessage",
            name="send_phase",
            field=models.CharField(
                choices=[
                    ("before_bot", "До бота"),
                    ("after_bot", "После бота / при эскалации"),
                    ("offline", "Вне графика"),
                ],
                db_index=True,
                default="before_bot",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="basemessage",
            name="sort_order",
            field=models.IntegerField(db_index=True, default=100),
        ),
        migrations.RunPython(populate_base_message_delivery, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="basemessage",
            options={"ordering": ("sort_order", "created_at")},
        ),
    ]
