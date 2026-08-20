# Phase 09 — Persistence & Multi-Tenant/User-Associated Data

## Objective

Add user-associated persistence so authenticated application users can own analysis history, without introducing SaaS multi-tenancy, communication connectors, or cloud databases in this phase.

PostgreSQL is the production database. SQLite is the local/default test backend. Raw communication bodies are not stored. Persistence sits beside the AI provider, not inside it.

## Business Value

- Authenticated users can retrieve and delete their own analysis history.
- Verified OIDC `issuer` + `subject` map to a stable internal user UUID without using email.
- Analyze remains usable in development without a database; persistence is automatic only when both a database and an authenticated principal are present.

## Status

Phase 9 is **in progress**.

- **9A is completed:** SQLAlchemy 2.x (sync), Alembic, ORM models, repository interfaces and SQLite-tested implementations, production `DATABASE_URL` fail-closed rules.
- **9B is completed:** verified issuer on `AuthenticatedPrincipal`, IdentityResolver, persist-after-analyze, owned history endpoints, IDOR-safe 404 semantics. No raw message-body persistence. No cloud database.
- **9C is implementation complete — remote PostgreSQL CI verification pending.** Repository changes add a GitHub `postgres:16` service-container job, Alembic upgrade/downgrade/upgrade against ephemeral PostgreSQL, PostgreSQL repository/readiness tests, and a database readiness probe. Do not mark 9C Completed until that GitHub job has passed after a reviewed commit/push. Do not deploy this image. There is still no cloud database.
- **9D is not started:** cloud persistence verification, managed-database cost decision, Phase 9 ADRs, final documentation.

Phase 9B implements **user-associated ownership isolation**. It does not implement enterprise tenants, organizations, workspaces, membership, tenant RBAC, shared mailboxes, or a multi-tenant Entra application. Multiple authenticated users are not SaaS multi-tenancy.

## Deliverables

- [x] Phase 9A — Persistence Foundation
- [x] Phase 9B — User Ownership & Analysis History
- [ ] Phase 9C — PostgreSQL Integration & Deployment Prep (implementation complete; remote CI pending)
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
- [x] Implement PostgreSQL CI service container, migration round trip, and readiness (9C repository work)
- [ ] Confirm GitHub PostgreSQL integration job after reviewed commit/push (9C remote verification)
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
- PostgreSQL is the production target. SQLite remains the local/default test backend. GitHub CI uses ephemeral `postgres:16`.
- Alembic migrations are verified against real PostgreSQL in CI. They are not run on application startup and must not be run from every Container Apps/Fargate replica.
- Canonical migration command: `alembic upgrade head`. This is a one-time operator/deployment action.
- Migration identity is not necessarily the runtime application database identity. Migration credentials need DDL rights. Runtime credentials should eventually need only application DML rights where practical. Azure MI / AWS IAM database auth is not implemented in 9C.
- The CI database user may own the ephemeral database and therefore perform DDL. That is test infrastructure, not the production runtime credential design.
- `GET /health` remains process-only and does not query PostgreSQL. `GET /api/v1/readiness` probes the database with `SELECT 1` only when `DATABASE_URL` is configured. Persistence-disabled development stays ready. An unavailable database fails closed with HTTP 503 and a generic body.
- Alembic reads `DATABASE_URL` through a storage-level resolver. It does not load application Settings or OIDC configuration.
- Destructive `alembic downgrade base` is tested only against disposable CI PostgreSQL to prove reversibility. Production rollback remains expand/contract, forward-compatible migrations, and an explicit operator decision. Production must not automatically downgrade.
- No dual always-on managed databases. No cloud PostgreSQL is provisioned in 9C.
- Phase 9 ADRs are deferred to 9D.

## Phase 9C — PostgreSQL Integration

### Local vs CI

Default local `python -m pytest` does not require Docker or PostgreSQL. PostgreSQL-specific tests live under `tests/postgres/` and skip unless `ECI_POSTGRES_TEST_DATABASE_URL` is set. That variable is validated before destructive migration work: scheme `postgresql+psycopg`, host `localhost` or `127.0.0.1`, and a database name containing `eci_test`. Arbitrary `DATABASE_URL` values are not reused for downgrade tests.

GitHub Actions job `postgres-integration` starts `postgres:16` as a service container with synthetic credentials `eci_test` / `eci_test` / `eci_test`. Those values are not secrets. The job permissions are `contents: read` only. It does not log in to Azure or AWS.

### Migration execution

Prepared sequence, not executed against cloud in 9C:

1. Run a one-time migration job/step: `alembic upgrade head`
2. Confirm success
3. Deploy application code compatible with that schema
4. Verify `GET /api/v1/readiness` when persistence is enabled
5. Handle destructive migrations as a separate explicit operator decision

Do not run migrations from application startup. Do not add a cloud migration step to `deploy.yml` yet: no Azure PostgreSQL or AWS RDS exists. That decision belongs to Phase 9D.

Offline compilation (`alembic upgrade head --sql`) is the Docker-free local check. It requires a syntactically valid PostgreSQL `DATABASE_URL` and does not connect.

### Deployment warning

Current Azure Container Apps and AWS ECS applications still do not have Phase 9 PostgreSQL infrastructure. Do not deploy the Phase 9C image. Do not set cloud `DATABASE_URL` in this phase.

## Acceptance Criteria

- [x] Previous API, authentication, and AI provider behavior unchanged when persistence is disabled
- [x] SQLite repository tests pass without Docker, network, or cloud
- [x] Production rejects missing `DATABASE_URL` and SQLite URLs
- [x] Development does not create an implicit local database file
- [x] History API and persist-after-analyze (Phase 9B)
- [ ] PostgreSQL CI job observed green on GitHub after reviewed commit/push (Phase 9C remote verification)

## Risks and Trade-offs

- Current Azure/AWS runtimes are not configured with `DATABASE_URL`. The Phase 9 image must not be deployed until Phase 9D provisions persistence, if that is the chosen cloud strategy.
- SQLite unit tests use portable JSON/UUID types. Real PostgreSQL dialect coverage is implemented in `tests/postgres/` and executed by GitHub CI, not by default local pytest.
- Post-inference save failure returns HTTP 200 without `analysis_id` so a paid result is not discarded.
- Duplicate paid inference on analyze retries is unchanged until idempotency is designed later.

## Lessons Learned

- Keeping `CommunicationAnalysisService` and `AIProvider` free of SQLAlchemy preserves the existing provider-independent analysis path.
- Identity resolution must complete before inference so a database outage cannot spend a provider call.
- Alembic should not boot full application Settings. Migration execution is not an OIDC concern.

## Next Phase

Phase 9D — Cloud Strategy & Final Documentation, after GitHub PostgreSQL CI is observed green.

Do not implement 9D in this phase. Do not deploy this revision.
