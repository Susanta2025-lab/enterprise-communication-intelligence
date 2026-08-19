# Phase 09 — Persistence & Multi-Tenant/User-Associated Data

## Objective

Add user-associated persistence so authenticated application users can own analysis history, without introducing SaaS multi-tenancy, communication connectors, or cloud databases in this phase.

PostgreSQL is the production database. SQLite is test-only. Raw communication bodies are not stored. Persistence sits beside the AI provider, not inside it.

## Business Value

- Analysis results can later be retrieved as history owned by an internal user UUID.
- OIDC `issuer` + `subject` map to a stable internal identity without using email.
- The AI provider contract and current analyze API remain unchanged until Phase 9B.

## Status

Phase 9 is **in progress**.

- **9A is completed:** SQLAlchemy 2.x (sync), Alembic, ORM models, repository interfaces and SQLite-tested implementations, production `DATABASE_URL` fail-closed rules. No analysis history API. No automatic persistence after analyze. No cloud database.
- **9B is not started:** IdentityResolver, issuer on the authenticated principal, persist-after-analyze, history endpoints, HTTP ownership semantics.
- **9C is not started:** PostgreSQL migration execution, CI service container, database readiness, deployment migration mechanics.
- **9D is not started:** cloud persistence verification, managed-database cost decision, Phase 9 ADRs, final documentation.

## Deliverables

- [x] Phase 9A — Persistence Foundation
- [ ] Phase 9B — User Ownership & Analysis History
- [ ] Phase 9C — PostgreSQL Integration & Deployment Prep
- [ ] Phase 9D — Cloud Strategy & Final Documentation

## Tasks

- [x] Add synchronous SQLAlchemy 2.x, Alembic, and psycopg 3
- [x] Implement `users`, `external_identities`, and `analyses` ORM models
- [x] Add `IdentityRepository` and `AnalysisRepository` interfaces
- [x] Implement SQLAlchemy repositories with ownership in SQL
- [x] Add an initial Alembic migration
- [x] Require PostgreSQL `DATABASE_URL` in production; allow omitting it in development
- [x] Cover repositories with Docker-free SQLite unit tests
- [ ] Resolve OIDC principal to internal user and persist analyses (9B)
- [ ] Add owned history HTTP endpoints (9B)
- [ ] Run Alembic against PostgreSQL in CI (9C)
- [ ] Document cloud database strategy and ADRs (9D)

## Architectural Decisions

- Persistence lives in `app/infrastructure/storage/` behind domain repository interfaces.
- Internal user UUID is the ownership key. External identity is unique `(issuer, subject)`.
- No tenant, organization, or workspace tables in Phase 9.
- No raw message body, sender, recipients, subject line, tokens, or JWT claims in storage.
- `create_all()` is test-only. Production schema changes use Alembic.
- Phase 9 ADRs are deferred to 9D.

## Acceptance Criteria

- [x] Previous API, authentication, and AI provider behavior unchanged
- [x] SQLite repository tests pass without Docker, network, or cloud
- [x] Production rejects missing `DATABASE_URL` and SQLite URLs
- [x] Development does not create an implicit local database file
- [ ] History API and persist-after-analyze (Phase 9B)
- [ ] PostgreSQL CI and readiness (Phase 9C)

## Risks and Trade-offs

- Cloud Azure/AWS runtimes are not yet configured with `DATABASE_URL`. Phase 9A must not be deployed until later subphases add that configuration.
- SQLite unit tests use portable JSON/UUID types; PostgreSQL dialect coverage is deferred to 9C.
- Duplicate paid inference on analyze retries is unchanged until idempotency is designed later.

## Lessons Learned

- Keeping `CommunicationAnalysisService` and `AIProvider` free of SQLAlchemy preserves the existing provider-independent analysis path.

## Next Phase

Phase 9B — User Ownership & Analysis History.

Do not implement 9B in this phase.
