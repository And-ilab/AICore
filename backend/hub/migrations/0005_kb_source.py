# Source attribute for unified KB admin (manual upload vs SUZ Bitrix).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0004_assistant_kb_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactcenterknowledgebase",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Ручная загрузка"),
                    ("suz_bitrix", "СУЗ Битрикс"),
                ],
                db_index=True,
                default="manual",
                max_length=32,
            ),
        ),
    ]
