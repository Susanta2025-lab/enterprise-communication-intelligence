# ADR-014: Cloud PostgreSQL Deployment Strategy

## Status

Accepted

The decision is documented. PostgreSQL is the production persistence technology. Phase 9 proves dialect compatibility with ephemeral GitHub Actions PostgreSQL. No Azure Database for PostgreSQL and no Amazon RDS instance is provisioned.

## Date

Phase 9 (Persistence)

## Context

ECI already runs the same application image on Azure Container Apps and Amazon ECS Fargate. Phase 9 needs a production database strategy that:

- keeps the application cloud-portable
- avoids standing managed-database cost while there is no real production workload
- does not create a shared cross-cloud database
- does not imply active-active multi-cloud data replication

Phase 9C already proved:

- GitHub Actions `postgres:16` service healthy
- `alembic upgrade head` to revision `9a0001`
- `alembic downgrade base` with application schema removed
- `alembic upgrade head` again
- 34 PostgreSQL integration tests

Verified CI run: `32336909759`. That run is not a managed-database test.

## Decision

Select **Option C**: a cloud-portable PostgreSQL application, proven by ephemeral CI, with a managed database provisioned only for an actual deployment that needs persistence.

```text
Same ECI code, ORM, migrations, and repositories

CI proof:
GitHub Actions → ephemeral postgres:16 → Alembic round-trip → 34 tests

Future production:
provision PostgreSQL only beside the deployment that needs it
```

Cloud portability means the same application model, repository layer, Alembic migration, and PostgreSQL URL contract. It does not mean Azure Database for PostgreSQL and Amazon RDS have identical operational, networking, or authentication semantics. Those remain future infrastructure decisions.

### Option A — one shared PostgreSQL across Azure and AWS

Rejected as the default production architecture. This topology is possible, but it is not selected as the preferred design.

```text
Azure Container Apps
          \
           → one DB hosted in one cloud
          /
Amazon ECS
```

Problems:

- cross-cloud latency
- cross-cloud data-transfer cost
- asymmetric availability: one cloud outage becomes persistence failure for the other
- network and private-connectivity complexity
- one cloud becomes the persistence dependency for the other
- a weaker multi-cloud demonstration, because the data plane is single-cloud

### Option B — standing Azure PostgreSQL plus standing Amazon RDS

Rejected for the current portfolio/project phase.

Reasons:

- recurring cost with no current real production workload
- consistency and replication complexity
- failover architecture outside project scope
- data synchronization would become a separate distributed-systems project
- unnecessary for demonstrating provider-independent application architecture

Two independent databases are not automatic active-active multi-cloud. Phase 9 must not claim that persistent data replicates seamlessly between Azure and AWS.

### Option C — portable application plus CI proof (selected)

Cost, security, and complexity trade-offs:

| Concern | Option C effect |
|---|---|
| Cost | no standing managed-database bill until a real deployment needs persistence |
| Security | no cloud DB credentials, private endpoints, or firewall holes created in Phase 9 |
| Complexity | application portability is proven; production networking remains future work |
| Proof | real PostgreSQL dialect coverage in CI, not a claim of managed HA |

### Future Azure path (not implemented)

```text
Azure Container Apps
→ private/controlled connectivity
→ Azure Database for PostgreSQL Flexible Server
→ PostgreSQL database
→ ECI schema
```

Possible later credential options:

1. secret/reference-based PostgreSQL credential
2. Microsoft Entra-based PostgreSQL authentication where practical

Entra database authentication is not implemented. No Azure PostgreSQL resource is created in Phase 9.

### Future AWS path (not implemented)

```text
ECS Fargate
→ private/controlled connectivity
→ Amazon RDS for PostgreSQL
→ PostgreSQL database
→ ECI schema
```

Possible later credential options:

1. secret-managed DB credential
2. RDS IAM database authentication where operationally appropriate

IAM database authentication is not implemented. No RDS instance is created in Phase 9.

### Current application contract

`DATABASE_URL` is the persistence contract.

- Development: omitted → persistence disabled → analyze-only mode supported
- Explicit SQLite: allowed for development and default local tests
- Production: required, scheme `postgresql+psycopg://`

A production deployment must not permanently store a literal database password in source code, GitHub, the container image, or committed config. Future injection can use Azure Key Vault / secret reference / identity-based access, or AWS Secrets Manager / task identity / IAM-based alternatives. None of those are implemented in Phase 9.

### Runtime identity versus migration identity

Runtime application identity is not the migration identity.

- Migration identity needs DDL/schema-migration privileges.
- Runtime application identity should eventually need `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on the application schema only.
- The CI database user may own the disposable database. That is test infrastructure, not the production credential design.

### Migration execution

Canonical command: `alembic upgrade head`.

Operational principle: migrate once, deploy the application, then verify readiness.

Do not auto-migrate from FastAPI startup. Do not let every Container Apps or ECS replica race to migrate. Do not automatically downgrade production.

CI tests downgrade reversibility on a disposable database. Production rollback should prefer forward fixes, expand/contract migrations, and backward-compatible application deployment. `alembic downgrade` in production requires an explicit operator decision.

## Alternatives Considered

Covered as Option A and Option B above.

## Consequences

- Phase 9 can complete without creating managed-database cost.
- Current Azure Container Apps and ECS environments remain without `DATABASE_URL`.
- Deploying the Phase 9 image to those environments without a colocated database would fail production startup or leave persistence unconfigured; Phase 9D does not deploy.

## Benefits

- honest cost control
- cloud-portable persistence implementation
- CI dialect proof without standing infrastructure

## Trade-offs

- no live managed-database connection, private networking, HA, backup, or DR proof
- operators must provision a colocated database before any real persisted deployment
- secret injection remains environment-variable `DATABASE_URL` today

## Deferred Work

- provisioning Azure PostgreSQL or Amazon RDS
- private networking, TLS to the database, and firewalling
- Key Vault / Secrets Manager injection
- Entra or RDS IAM database authentication
- managed backups, PITR, HA, failover, and cross-region DR
- adding a migration step to `deploy.yml` when a real database exists

## Related Components

- `.github/workflows/ci.yml` (PostgreSQL integration job)
- [Cloud PostgreSQL strategy](../cloud/persistence.md)
- [Deployment](../cloud/deployment.md)
- ADR-011 (GitHub Actions OIDC CI/CD)
- ADR-012 (PostgreSQL Persistence Architecture)
