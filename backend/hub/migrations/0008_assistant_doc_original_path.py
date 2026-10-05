from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0007_model_params_preset"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantknowledgebasedocument",
            name="original_relpath",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
