# Phase 09 — Persistence & Multi-Tenant/User-Associated Data

## Objective

Add user-associated persistence so authenticated application users can own analysis history, without introducing SaaS multi-tenancy, communication connectors, or standing managed cloud databases in this phase.

PostgreSQL is the production database. SQLite is the local/default test backend. Raw communication bodies are not stored. Persistence sits beside the AI provider, not inside it.

## Business Value

- Authenticated users can retrieve and delete their own analysis history.
- Verified OIDC `issuer` + `subject` map to a stable internal user UUID without using email.
- Analyze remains usable in development without a database; persistence is automatic only when both a database and an authenticated principal are present.
- PostgreSQL compatibility is proven in CI without creating standing managed-database cost.

## Status

Phase 9 is **Completed**.

- **9A is completed:** SQLAlchemy 2.x (sync), Alembic, ORM models, repository interfaces and SQLite-tested implementations, production `DATABASE_URL` fail-closed rules.
- **9B is completed:** verified issuer on `AuthenticatedPrincipal`, IdentityResolver, persist-after-analyze, owned history endpoints, IDOR-safe 404 semantics. No raw message-body persistence. No cloud database.
- **9C is completed:** GitHub Actions run `32336909759`. Jobs: Lint and test success; PostgreSQL integration success. Sequence: `postgres:16` healthy → `alembic upgrade head` → revision `9a0001` → `alembic downgrade base` → application schema removed → `alembic upgrade head` → `tests/postgres`: 34 passed. No managed cloud database was tested.
- **9D is completed:** ADR-012, ADR-013, and ADR-014; cloud-portable PostgreSQL strategy with CI-based dialect proof; shared cross-cloud DB and dual standing managed DBs rejected for this phase; future per-cloud colocated topology documented conceptually only.

Phase 9 implements **user-associated ownership isolation**. It does not implement enterprise tenants, organizations, workspaces, membership, tenant RBAC, shared mailboxes, or a multi-tenant Entra application. Multiple authenticated users are not SaaS multi-tenancy.

## Deliverables

- [x] Phase 9A — Persistence Foundation
- [x] Phase 9B — User Ownership & Analysis History
- [x] Phase 9C — PostgreSQL Integration & CI
- [x] Phase 9D — Cloud Strategy & Final Documentation

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
- [x] Implement PostgreSQL CI service container, migration round trip, and readiness (9C)
- [x] Confirm GitHub PostgreSQL integration job after reviewed commit/push (run `32336909759`)
- [x] Document cloud database strategy and ADRs (9D)

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
- Canonical migration command: `alembic upgrade head`. This is a one-time operator/deployment action: migrate once, deploy app, verify readiness.
- Migration identity is not the runtime application database identity. Migration credentials need DDL rights. Runtime credentials should eventually need only application DML rights where practical. Azure Entra / AWS IAM database auth is not implemented.
- The CI database user may own the ephemeral database and therefore perform DDL. That is test infrastructure, not the production runtime credential design.
- `GET /health` remains process-only and does not query PostgreSQL. `GET /api/v1/readiness` probes the database with `SELECT 1` only when `DATABASE_URL` is configured. Persistence-disabled development stays ready. An unavailable database fails closed with HTTP 503 and a generic body.
- Alembic reads `DATABASE_URL` through a storage-level resolver. It does not load application Settings or OIDC configuration.
- Destructive `alembic downgrade base` is tested only against disposable CI PostgreSQL to prove reversibility. Production rollback remains expand/contract, forward-compatible migrations, and an explicit operator decision. Production must not automatically downgrade.
- Selected cloud strategy (Option C): portable application + ephemeral PostgreSQL CI proof + provision a managed database only for an actual deployment. Shared Azure/AWS database rejected. Dual standing managed databases rejected for the current phase.
- Future real deployments should colocate PostgreSQL with the runtime (ACA → Azure-local PostgreSQL; ECS → AWS-local RDS). Those resources are not provisioned in Phase 9. Data does not replicate across clouds.

See [ADR-012](../decisions/ADR-012-postgresql-persistence-architecture.md), [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md), and [ADR-014](../decisions/ADR-014-cloud-postgresql-deployment-strategy.md).

## Phase 9C — PostgreSQL Integration

### Local vs CI

Default local `python -m pytest` does not require Docker or PostgreSQL. PostgreSQL-specific tests live under `tests/postgres/` and skip unless `ECI_POSTGRES_TEST_DATABASE_URL` is set. That variable is validated before destructive migration work: scheme `postgresql+psycopg`, host `localhost` or `127.0.0.1`, and a database name containing `eci_test`. Arbitrary `DATABASE_URL` values are not reused for downgrade tests.

GitHub Actions job `postgres-integration` starts `postgres:16` as a service container with synthetic test credentials. Those values are not production secrets. The job permissions are `contents: read` only. It does not log in to Azure or AWS.

Verified run: `32336909759` (34 PostgreSQL tests passed; migration round-trip completed).

### Migration execution

1. Run a one-time migration job/step: `alembic upgrade head`
2. Confirm success
3. Deploy application code compatible with that schema
4. Verify `GET /api/v1/readiness` when persistence is enabled
5. Handle destructive migrations as a separate explicit operator decision

Do not run migrations from application startup. Do not add a cloud migration step to `deploy.yml` yet: no Azure PostgreSQL or AWS RDS exists.

Offline compilation (`alembic upgrade head --sql`) is the Docker-free local check. It requires a syntactically valid PostgreSQL `DATABASE_URL` and does not connect.

### Deployment warning

Current Azure Container Apps and AWS ECS applications still do not have Phase 9 PostgreSQL infrastructure. Do not deploy the Phase 9 image. Do not set cloud `DATABASE_URL` in this phase.

## Acceptance Criteria

- [x] Previous API, authentication, and AI provider behavior unchanged when persistence is disabled
- [x] SQLite repository tests pass without Docker, network, or cloud
- [x] Production rejects missing `DATABASE_URL` and SQLite URLs
- [x] Development does not create an implicit local database file
- [x] History API and persist-after-analyze (Phase 9B)
- [x] PostgreSQL CI job observed green on GitHub after reviewed commit/push (Phase 9C, run `32336909759`)
- [x] Cloud persistence strategy and ADRs documented (Phase 9D)

## Risks and Trade-offs

- Current Azure/AWS runtimes are not configured with `DATABASE_URL`. The Phase 9 image must not be deployed until a colocated PostgreSQL database exists.
- SQLite unit tests use portable JSON/UUID types. Real PostgreSQL dialect coverage is implemented in `tests/postgres/` and executed by GitHub CI, not by default local pytest.
- Post-inference save failure returns HTTP 200 without `analysis_id` so a paid result is not discarded.
- Duplicate paid inference on analyze retries is unchanged until idempotency is designed later.
- No managed backup, PITR, HA, private networking, or cross-cloud replication exists.

## Lessons Learned

- Keeping `CommunicationAnalysisService` and `AIProvider` free of SQLAlchemy preserves the existing provider-independent analysis path.
- Identity resolution must complete before inference so a database outage cannot spend a provider call.
- Alembic should not boot full application Settings. Migration execution is not an OIDC concern.
- Ephemeral CI PostgreSQL is sufficient dialect proof for this portfolio phase; standing managed databases would add cost without a production workload.

## Next Phase

Phase 10 — Communication Connectors.

Potential scope (not implemented here):

- Gmail
- Microsoft Graph / Outlook
- connector interfaces
- OAuth/token lifecycle architecture
- sync cursors
- source message ingestion and normalization

Phase 9 already supports future connectors by keeping `users.id` as a stable ownership FK and storing `source_type` plus optional `message_id` on analyses. Phase 9 does **not** contain connection records, OAuth token storage, message synchronization tables, or sync cursors. Raw communication body retention remains an explicit future decision.

Do not implement Phase 10 in this phase. Do not deploy this revision.
