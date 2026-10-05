from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0017_operator_photo_skills_base_delay"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operatorprofile",
            name="photo_url",
            field=models.TextField(blank=True, default=""),
        ),
    ]
