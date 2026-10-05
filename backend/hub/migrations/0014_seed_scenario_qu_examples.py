from django.db import migrations


def seed_qu_examples(apps, schema_editor):
    from hub.management.commands.seed_cc_scenarios import _ensure_example
    from hub.scenario_catalog import ALL_SCENARIOS, NO_HINT_EXAMPLES

    for intent_id, question in NO_HINT_EXAMPLES:
        _ensure_example(question, intent_id, "0014_seed")
    for payload in ALL_SCENARIOS:
        if payload.get("status") != "production":
            continue
        nodes = (payload.get("graph") or {}).get("nodes") or []
        start = next((node for node in nodes if node.get("type") == "start"), None)
        if not start:
            continue
        intent = str(start.get("intent_id") or payload["code"])
        for question in start.get("examples") or []:
            _ensure_example(question, intent, "0014_seed")


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0013_seed_dialog_scenarios"),
        ("qu", "0002_training_moderation"),
    ]

    operations = [
        migrations.RunPython(seed_qu_examples, migrations.RunPython.noop),
    ]
