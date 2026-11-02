from django.db import migrations


def seed_flowcharts(apps, schema_editor):
    from hub.scenario_catalog import FLOW_SCENARIOS
    from hub.scenario_service import upsert_from_catalog

    for payload in FLOW_SCENARIOS:
        upsert_from_catalog(payload, username="0030_flowcharts")


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0029_seed_flowchart_scenarios"),
    ]

    operations = [
        migrations.RunPython(seed_flowcharts, migrations.RunPython.noop),
    ]
