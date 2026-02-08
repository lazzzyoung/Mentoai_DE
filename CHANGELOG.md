# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project uses Semantic Versioning.

## [0.1.0] - 2026-02-08

### Added
- Async DB session normalization tests and app import smoke tests.
- RAG/Spark unit tests for core helper logic.
- GitHub Actions CI workflow for `uv run poe check`.
- Baseline Alembic migration script with initial user tables.

### Changed
- Unified API surface to `/api/v1` and merged roadmap/recommendation/analysis endpoints.
- Migrated roadmap response model to structured schema in `server/app/schemas/v1.py`.
- Improved async safety by offloading blocking LLM/vector-store calls to threadpool.
- Expanded README with stack/setup/task/API/CI guidance.
- Removed Docker Compose `version` field and architecture-specific platform pinning.

### Removed
- Deprecated `server/app/api/routes/v2.py`, `server/app/api/routes/v3.py`.
- Deprecated `server/app/schemas/v2.py`, `server/app/schemas/v3.py`.
