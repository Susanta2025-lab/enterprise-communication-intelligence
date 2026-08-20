# ADR-012: PostgreSQL Persistence Architecture

## Status

Accepted

The decision is implemented. Phase 9 stores user-owned analysis history behind domain repository and unit-of-work interfaces. PostgreSQL is the production dialect. SQLite is a local/test convenience only. Phase 9C proved the PostgreSQL path on GitHub Actions with ephemeral `postgres:16`. No managed cloud database is provisioned.

## Date

Phase 9 (Persistence)

## Context

Through Phase 8, ECI analyzed communications in a stateless request/response path. Authenticated callers could not retrieve previous analyses. Phase 9 requires:

- user-associated analysis history
- ownership isolation in every query
- portable persistence that does not couple the domain to Azure or AWS
- explicit schema migrations
- local tests that remain Docker-free by default

Constraints:

- `CommunicationAnalysisService` must remain AI-only
- raw communication bodies must not be stored
- production must fail closed without a PostgreSQL URL
- development must still support analyze-only mode when `DATABASE_URL` is omitted
- the application remains synchronous

## Decision

Use PostgreSQL as the production system of record, accessed through SQLAlchemy 2.x (synchronous) and psycopg 3.

```text
API
→ CommunicationAnalysisWorkflowService
→ domain IdentityRepository / AnalysisRepository / PersistenceUnitOfWork
← SQLAlchemy infrastructure (app/infrastructure/storage)
→ PostgreSQL
```

- Alembic owns schema changes. Canonical command: `alembic upgrade head`.
- SQLite is allowed only when explicitly configured for development or default local tests.
- Production (`APP_ENV=production`) requires `DATABASE_URL` with scheme `postgresql+psycopg://`.
- Repository implementations live in infrastructure. Domain interfaces remain SQLAlchemy-free.
- `CommunicationAnalysisService` does not import persistence types.

### Data model

Three application tables:

| Table | Role |
|---|---|
| `users` | Opaque internal UUID ownership key |
| `external_identities` | Unique `(issuer, subject)` mapping onto `users.id` |
| `analyses` | User-owned analysis history |

Identifier classes remain distinct:

| Identifier | Meaning |
|---|---|
| `request_id` | Operational HTTP correlation (`X-Request-ID`) |
| `analysis_id` | Persisted analysis resource UUID |
| `message_id` | Caller-supplied business message identifier |
| `user_id` | Internal ownership UUID |

### Data minimization

Persisted analysis rows store structured results (`summary`, `priority`, `category`, `action_items`, optional `draft_reply`) plus `source_type` and optional `message_id`. They do not store raw communication body, sender, recipients, subject line, JWT, tokens, email, or display name.

## Alternatives Considered

- **Document database** — not selected for this system. ECI's ownership queries, foreign keys, and Alembic migrations fit a relational model.
- **Azure Cosmos DB or Amazon DynamoDB** — not selected. Either would introduce a cloud-specific persistence fork. ECI needs one portable schema and repository layer for Azure and AWS deployments.
- **Cloud-specific persistence implementations** — not selected. Azure and AWS deployments must share one schema, ORM, and repository layer.
- **SQLModel** — not selected. SQLAlchemy 2.x plus Pydantic v2 already cover ORM and API models; a further wrapper is unnecessary for this codebase.
- **Async database migration of the entire application** — not selected. The current stack is synchronous. An async rewrite is outside Phase 9 scope.

## Consequences

- The same application code can target SQLite in local tests and PostgreSQL in CI and future production.
- Schema evolution is explicit and reviewable through Alembic revision `9a0001`.
- Persistence is optional in development: omitting `DATABASE_URL` keeps analyze-only behavior.
- Production cannot start without PostgreSQL configuration, even though no managed database exists yet.

## Benefits

- cloud-portable relational persistence
- ownership isolation in SQL rather than in application filters
- Docker-free local tests
- AI orchestration remains independent of storage

## Trade-offs

- SQLite cannot prove JSONB, native UUID, `timestamptz`, or Alembic upgrade/downgrade fidelity
- no managed production database exists yet
- operators must inject `DATABASE_URL`; Key Vault / Secrets Manager remain later work

## Deferred Work

- Azure Database for PostgreSQL Flexible Server
- Amazon RDS for PostgreSQL
- private networking, HA, backups, PITR, and cross-region DR
- passwordless Entra or RDS IAM database authentication
- expand/contract migrations beyond the initial schema

## Related Components

- `app/infrastructure/storage/`
- `app/domain/interfaces/`
- `alembic/versions/`
- [Persistence architecture](../architecture/persistence.md)
- [Cloud PostgreSQL strategy](../cloud/persistence.md)
- ADR-001 (Clean Architecture)
- ADR-013 (User Identity and Ownership)
- ADR-014 (Cloud PostgreSQL Deployment Strategy)
