-- First-boot init for pgvector/pgvector:pg16 containers.
-- Vector ANN indexes are created by Django migrations (ingest.0001 / 0003)
-- and can be re-applied via infra/test/sql/ensure_pgvector.sql.

CREATE EXTENSION IF NOT EXISTS vector;
