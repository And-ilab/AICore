from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0016_base_message_channels_phase_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="operatorprofile",
            name="photo_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="operatorprofile",
            name="skill_tags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="basemessage",
            name="delay_seconds",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Задержка перед отправкой (hold / mid-dialog), секунды",
            ),
        ),
        migrations.AlterField(
            model_name="basemessage",
            name="send_phase",
            field=models.CharField(
                choices=[
                    ("before_bot", "До бота"),
                    ("after_bot", "После бота / при эскалации"),
                    ("mid_dialog", "В середине диалога (hold)"),
                    ("hold", "Ожидание ответа оператора"),
                    ("offline", "Вне графика"),
                ],
                db_index=True,
                default="before_bot",
                max_length=32,
            ),
        ),
    ]
