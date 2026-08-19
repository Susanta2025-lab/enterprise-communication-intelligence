# Phase 09 — Persistence & Multi-Tenant/User-Associated Data

## Objective

Add user-associated persistence so authenticated application users can own analysis history, without introducing SaaS multi-tenancy, communication connectors, or cloud databases in this phase.

PostgreSQL is the production database. SQLite is test-only. Raw communication bodies are not stored. Persistence sits beside the AI provider, not inside it.

## Business Value

- Authenticated users can retrieve and delete their own analysis history.
- Verified OIDC `issuer` + `subject` map to a stable internal user UUID without using email.
- Analyze remains usable in development without a database; persistence is automatic only when both a database and an authenticated principal are present.

## Status

Phase 9 is **in progress**.

- **9A is completed:** SQLAlchemy 2.x (sync), Alembic, ORM models, repository interfaces and SQLite-tested implementations, production `DATABASE_URL` fail-closed rules.
- **9B is completed:** verified issuer on `AuthenticatedPrincipal`, IdentityResolver, persist-after-analyze, owned history endpoints, IDOR-safe 404 semantics. No raw message-body persistence. No cloud database. Do not deploy this image until Phase 9C/9D provision PostgreSQL.
- **9C is not started:** PostgreSQL migration execution, CI service container, database readiness, deployment migration mechanics.
- **9D is not started:** cloud persistence verification, managed-database cost decision, Phase 9 ADRs, final documentation.

Phase 9B implements **user-associated ownership isolation**. It does not implement enterprise tenants, organizations, workspaces, membership, tenant RBAC, shared mailboxes, or a multi-tenant Entra application. Multiple authenticated users are not SaaS multi-tenancy.

## Deliverables

- [x] Phase 9A — Persistence Foundation
- [x] Phase 9B — User Ownership & Analysis History
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
- [x] Resolve OIDC principal to internal user and persist analyses (9B)
- [x] Add owned history HTTP endpoints (9B)
- [ ] Run Alembic against PostgreSQL in CI (9C)
- [ ] Document cloud database strategy and ADRs (9D)

## Architectural Decisions

- Persistence lives in `app/infrastructure/storage/` behind domain repository interfaces.
- Internal user UUID is the ownership key. External identity is unique `(issuer, subject)` from the verified JWT.
- `CommunicationAnalysisService` remains AI-only. A workflow service resolves identity, calls AI, then persists.
- Database transactions are never held open during a provider call. Identity failure before AI returns 503 with zero provider calls.
- History endpoints reuse `communications:analyze`. Cross-user get/delete return 404, not 403.
- No tenant, organization, or workspace tables in Phase 9.
- No raw message body, sender, recipients, subject line, tokens, or JWT claims in storage.
- `create_all()` is test-only. Production schema changes use Alembic.
- Phase 9 ADRs are deferred to 9D.

## Acceptance Criteria

- [x] Previous API, authentication, and AI provider behavior unchanged when persistence is disabled
- [x] SQLite repository tests pass without Docker, network, or cloud
- [x] Production rejects missing `DATABASE_URL` and SQLite URLs
- [x] Development does not create an implicit local database file
- [x] History API and persist-after-analyze (Phase 9B)
- [ ] PostgreSQL CI and readiness (Phase 9C)

## Risks and Trade-offs

- Current Azure/AWS runtimes are not configured with `DATABASE_URL`. The Phase 9B image must not be deployed until later subphases add that configuration.
- SQLite unit tests use portable JSON/UUID types; PostgreSQL dialect coverage is deferred to 9C.
- Post-inference save failure returns HTTP 200 without `analysis_id` so a paid result is not discarded.
- Duplicate paid inference on analyze retries is unchanged until idempotency is designed later.

## Lessons Learned

- Keeping `CommunicationAnalysisService` and `AIProvider` free of SQLAlchemy preserves the existing provider-independent analysis path.
- Identity resolution must complete before inference so a database outage cannot spend a provider call.

## Next Phase

Phase 9C — PostgreSQL Integration & Deployment Prep.

Do not implement 9C in this phase. Do not deploy this revision.
