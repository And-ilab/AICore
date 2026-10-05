import pgvector.django.vector
from django.db import migrations, models


def enable_pgvector(_apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")


def create_vector_index(_apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX cc_prod_embedding_hnsw_idx "
            "ON cc_production USING hnsw "
            "(embedding vector_cosine_ops)"
        )


def drop_vector_index(_apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP INDEX IF EXISTS cc_prod_embedding_hnsw_idx"
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.RunPython(
            enable_pgvector,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name="KnowledgeIngestEvent",
            fields=[
                (
                    "event_id",
                    models.UUIDField(editable=False, primary_key=True, serialize=False),
                ),
                ("article_id", models.BigIntegerField(db_index=True)),
                ("version_id", models.BigIntegerField(blank=True, null=True)),
                ("event_type", models.CharField(max_length=64)),
                ("checksum", models.CharField(blank=True, max_length=80)),
                ("outcome", models.CharField(max_length=32)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("-received_at",)},
        ),
        migrations.CreateModel(
            name="CCProductionChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("article_id", models.BigIntegerField(db_index=True)),
                ("version_id", models.BigIntegerField()),
                ("chunk_index", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=500)),
                ("content", models.TextField()),
                ("permalink", models.URLField(max_length=1000)),
                ("locale", models.CharField(max_length=8)),
                ("visibility_scope", models.JSONField(default=list)),
                ("checksum", models.CharField(max_length=80)),
                ("embedding_model", models.CharField(max_length=255)),
                (
                    "embedding",
                    pgvector.django.vector.VectorField(dimensions=1024),
                ),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True),
                ),
                ("indexed_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "cc_production",
                "ordering": ("article_id", "chunk_index"),
                "indexes": [
                    models.Index(
                        fields=["article_id", "is_active"],
                        name="cc_prod_article_active_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("article_id", "version_id", "chunk_index"),
                        name="cc_prod_article_version_chunk_uniq",
                    )
                ],
            },
        ),
        migrations.RunPython(
            create_vector_index,
            reverse_code=drop_vector_index,
        ),
    ]
