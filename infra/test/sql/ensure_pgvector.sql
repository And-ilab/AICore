-- TEST/PROD data tier: pgvector extension + vector ANN indexes.
-- Idempotent — safe to re-run after migrate.
-- Applied by: infra/test/verify-data-tier.sh (or deploy.sh db-verify)

CREATE EXTENSION IF NOT EXISTS vector;

-- cc_production HNSW (cosine) — also created by ingest.0001 / 0003 migrations.
CREATE INDEX IF NOT EXISTS cc_prod_embedding_hnsw_idx
    ON cc_production
    USING hnsw (embedding vector_cosine_ops);

-- Composite lookup index from CCProductionChunk.Meta.indexes
CREATE INDEX IF NOT EXISTS cc_prod_article_active_idx
    ON cc_production (article_id, is_active);
