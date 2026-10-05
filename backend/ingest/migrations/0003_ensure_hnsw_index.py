from django.db import migrations


def ensure_hnsw_index(_apps, schema_editor):
    """Idempotent repair for TEST/PROD if HNSW was dropped or volume restored bare."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS cc_prod_embedding_hnsw_idx "
        "ON cc_production USING hnsw (embedding vector_cosine_ops)"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0002_suzreconcilestate"),
    ]

    operations = [
        migrations.RunPython(
            ensure_hnsw_index,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
