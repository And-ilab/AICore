from django.db import migrations


def seed_scenarios(apps, schema_editor):
    from hub.scenario_catalog import ALL_SCENARIOS
    from hub.scenario_service import upsert_from_catalog

    for payload in ALL_SCENARIOS:
        upsert_from_catalog(payload, username="0013_seed")


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0012_dialog_scenarios"),
    ]

    operations = [
        migrations.RunPython(seed_scenarios, migrations.RunPython.noop),
    ]
