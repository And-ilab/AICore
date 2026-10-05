# Generated manually for assistant_* vector index (isolated from cc_production)

import pgvector.django.vector
from django.db import migrations, models


def create_vector_index(_apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS asst_prod_embedding_hnsw_idx "
            "ON assistant_production USING hnsw "
            "(embedding vector_cosine_ops)"
        )


def drop_vector_index(_apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP INDEX IF EXISTS asst_prod_embedding_hnsw_idx"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0003_ensure_hnsw_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantProductionChunk",
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
                ("kb_slug", models.SlugField(db_index=True, max_length=200)),
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
                "db_table": "assistant_production",
                "ordering": ("kb_slug", "article_id", "chunk_index"),
                "indexes": [
                    models.Index(
                        fields=["kb_slug", "article_id", "is_active"],
                        name="asst_prod_active_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "kb_slug",
                            "article_id",
                            "version_id",
                            "chunk_index",
                        ),
                        name="asst_prod_chunk_uniq",
                    )
                ],
            },
        ),
        migrations.RunPython(
            create_vector_index,
            reverse_code=drop_vector_index,
        ),
    ]
