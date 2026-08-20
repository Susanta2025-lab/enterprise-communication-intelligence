# Persistence Architecture

Phase 9 adds user-owned analysis history behind domain repository interfaces. PostgreSQL is the production system of record. SQLite is a local/test convenience. No managed Azure or AWS database is provisioned.

See [ADR-012](../decisions/ADR-012-postgresql-persistence-architecture.md), [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md), and [ADR-014](../decisions/ADR-014-cloud-postgresql-deployment-strategy.md). Cloud topology is documented in [Cloud PostgreSQL strategy](../cloud/persistence.md).

## Implemented persistence path

```text
Client
→ OIDC JWT
→ TokenValidator
→ AuthenticatedPrincipal (issuer, subject)
→ IdentityResolver
→ users / external_identities
→ CommunicationAnalysisWorkflowService
   ├── CommunicationAnalysisService → AIProvider → Microsoft Foundry / Amazon Bedrock / mock
   └── AnalysisHistoryService → AnalysisRepository → PostgreSQL
```

`CommunicationAnalysisService` remains AI-only. Persistence sits beside it, not inside it. Through Phase 8 the runtime was stateless with respect to application data. Phase 9 adds optional persistence when `DATABASE_URL` is configured. A deployment without that URL remains analyze-only.

## Identity classes

Do not conflate these identities:

| Class | Path | Purpose |
|---|---|---|
| User identity | Client → OIDC → ECI | Authenticate the API caller |
| Runtime AI identity | ECI → Foundry UAMI / Bedrock task role | Invoke the AI platform |
| Database identity | ECI → PostgreSQL when `DATABASE_URL` is set | Read and write application data. Managed cloud DB identity is future. |
| Deployment identity | GitHub → Azure / AWS | Build and deploy the image |

Internal `users.id` is an ownership key, not a login system and not a tenant.

## Data model

| Table | Contents |
|---|---|
| `users` | Opaque UUID primary key and timestamps. No PII columns. |
| `external_identities` | `issuer`, `subject`, unique `(issuer, subject)`, FK to `users.id` |
| `analyses` | User-owned structured analysis results |

Identifier classes:

| Identifier | Layer | Meaning |
|---|---|---|
| `request_id` | HTTP / telemetry | Server-generated operational correlation |
| `analysis_id` | persistence / API | Stored analysis resource UUID |
| `message_id` | business request | Caller-supplied source message identifier |
| `user_id` | persistence | Internal ownership UUID |

`source_type` and optional `message_id` are stored so later connectors can correlate analyses. Phase 9 does not store connection records, OAuth tokens, ingested messages, or sync cursors.

## Data minimization

Raw communication body is not persisted. Sender, recipients, subject line, email, display name, JWT, access token, refresh token, and scope claims are not stored. This is an intentional privacy decision. Future connector ingestion requires a separate explicit retention decision.

## Transaction architecture

Authenticated persist-after-analyze uses two short database transactions with no database transaction across the AI provider call:

```text
authenticate
→ authorize
→ resolve or create internal user (short transaction)
→ commit / close
→ AI inference
→ save analysis (new short transaction)
```

Holding a database transaction during inference would pin connections and locks for the duration of a network call to Microsoft Foundry or Amazon Bedrock. Separate transactions keep failure semantics clean: identity failure happens before a paid inference; persistence failure after inference cannot roll back a completed AI result.

## Failure semantics

| Condition | HTTP | AI calls | `analysis_id` |
|---|---|---|---|
| Persistence configured, identity/DB failure before AI | `503` | 0 | omitted |
| AI succeeds, persistence save fails | `200` with the analysis | 1 | omitted |
| Persistence disabled or no authenticated principal | `200` | 1 | omitted |
| Persistence configured, authenticated, save succeeds | `200` | 1 | returned |

A failed save does not retry the AI provider. That avoids discarding a paid inference result or paying twice.

History endpoints return `503` when persistence is configured and the database is unavailable. Unknown or cross-user resources return `404`.

## History ownership

```text
GET  /api/v1/analyses
GET  /api/v1/analyses/{analysis_id}
DELETE /api/v1/analyses/{analysis_id}
```

SQL scopes every query by `user_id`. No raw communication content is returned. History requires the same `communications:analyze` permission as analyze. History always requires an authenticated principal (`AUTH_MODE=disabled` returns `401`) and requires `DATABASE_URL` (`503` when omitted).

## DATABASE_URL

| Environment | Behavior |
|---|---|
| Development, `DATABASE_URL` omitted | Persistence disabled. Analyze-only mode. No local database file is created. |
| Development, explicit SQLite URL | Allowed for local tests and development. |
| Production | Required. Must use `postgresql+psycopg://`. SQLite is rejected. |

Do not put real credentials in documentation, source control, or the image. See [Cloud PostgreSQL strategy](../cloud/persistence.md) for future secret injection.

## Runtime versus migration database identity

Runtime application identity is not the migration identity.

- Migration identity needs DDL privileges to run `alembic upgrade head`.
- Runtime application identity should eventually need only `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on the application schema.
- The CI database user may own a disposable database. That is not the production runtime design.

## Migration execution

Canonical command:

```bash
alembic upgrade head
```

Selected operational principle:

```text
migrate once
→ deploy application
→ verify GET /api/v1/readiness
```

Do not auto-migrate from FastAPI startup. Do not let every Azure Container Apps replica or ECS task race to migrate. Do not automatically downgrade production.

Alembic reads `DATABASE_URL` through a storage-level resolver. It does not load application Settings or OIDC configuration.

Current head revision: `9a0001`.

## Rollback and expand/contract

CI tests `alembic downgrade base` on disposable PostgreSQL to prove reversibility. That is not a production rollback runbook.

Production schema change should prefer:

1. Stage A — add nullable or otherwise backward-compatible structures
2. Stage B — deploy application code that can use old and new shapes where needed
3. Stage C — migrate or backfill
4. Stage D — remove the old structure in a later release

`alembic downgrade` in production requires an explicit operator decision. Forward fixes are preferred.

## Readiness

| Endpoint | Meaning |
|---|---|
| `GET /health` | Process liveness only. Does not query PostgreSQL. |
| `GET /api/v1/health` | Versioned process metadata. Does not query PostgreSQL. |
| `GET /api/v1/readiness` | Application readiness. |

Readiness behavior:

- Persistence disabled: ready
- Persistence configured and `SELECT 1` succeeds: ready
- Persistence configured and the database is unavailable: `503` with `{"detail": "Persistence is currently unavailable."}`

No database host, error, or driver detail is returned.

## PostgreSQL verification matrix

| Capability | SQLite local | PostgreSQL CI |
|---|---|---|
| Repository behavior | yes | yes |
| Identity uniqueness `(issuer, subject)` | yes | yes |
| Ownership isolation | yes | yes |
| Foreign-key cascade | yes | yes |
| JSON round-trip | yes | yes |
| JSONB type | n/a (portable JSON) | yes |
| UUID database type | emulated / portable | yes |
| `timestamptz` | limited fidelity | yes |
| Alembic migration | metadata / offline SQL | yes |
| Upgrade / downgrade / upgrade | no | yes |
| `DELETE` rowcount | dialect-dependent | verified PostgreSQL |

Default local `python -m pytest` skips `tests/postgres/` unless `ECI_POSTGRES_TEST_DATABASE_URL` is set. GitHub Actions job `PostgreSQL integration` on run `32336909759` executed the migration round-trip and 34 PostgreSQL tests. That run did not use Azure Database for PostgreSQL or Amazon RDS. It does not prove managed-service networking, production performance, HA, backup, PITR, or cloud IAM database authentication.

## Proven versus not proven

**Proven**

- SQLAlchemy repository and unit-of-work architecture
- Alembic migrations
- `users` / `external_identities` / `analyses` schema
- UUID, JSONB, and `timestamptz` behavior on PostgreSQL
- composite issuer+subject uniqueness
- foreign-key cascades
- PostgreSQL ownership filtering and `DELETE` rowcount
- PostgreSQL unit-of-work transaction semantics
- database readiness probe
- migration upgrade / downgrade / upgrade
- 34 real PostgreSQL tests
- SQLite local test strategy

**Not yet proven**

- Azure managed PostgreSQL connection
- Amazon RDS connection
- private networking to a database
- passwordless Azure database identity
- AWS RDS IAM database authentication
- managed HA / failover
- backups / PITR
- managed database monitoring
- cross-region disaster recovery
- database replication across clouds

## Phase 10 compatibility

Phase 9 deliberately keeps `users.id` as a stable ownership foreign key. Existing analyses already store `source_type` and optional `message_id`.

Phase 9 does **not** contain:

- connection records
- OAuth token storage
- message synchronization tables
- sync cursors

Those remain Phase 10 — Communication Connectors.

## Performance and operations (deferred)

Do not implement premature optimizations. Future production work should consider connection-pool sizing, managed-database connection limits, indexes driven by observed queries, pagination beyond the current bounded `limit`/`offset` page, retention/archival, and migration timing. Managed backup, PITR, replication, cross-region DR, and failover are deferred because no managed production database exists. CI PostgreSQL is not production backup proof.

## Multi-cloud claim

Correct: ECI's persistence implementation is cloud-portable and PostgreSQL-compatible.

Incorrect: ECI currently replicates persistent data between Azure and AWS.
