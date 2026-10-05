from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0005_channelconnection_department_dialogevent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialog",
            name="client_external_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=160,
            ),
        ),
        migrations.AddField(
            model_name="dialog",
            name="entry_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="dialog",
            name="locale",
            field=models.CharField(blank=True, default="ru", max_length=16),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="external_message_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=160,
            ),
        ),
    ]
