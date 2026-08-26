# Cloud PostgreSQL Strategy

Phase 9 selects a **cloud-portable PostgreSQL architecture with CI-based production-dialect proof**. The application can persist to PostgreSQL. Phase 9 does not create Azure Database for PostgreSQL, Amazon RDS, one shared cross-cloud database, or two permanently running managed databases.

See [ADR-014](../decisions/ADR-014-cloud-postgresql-deployment-strategy.md) and [Persistence architecture](../architecture/persistence.md).

## Selected strategy (Option C)

```text
Same ECI application, ORM, Alembic migrations, and repositories

CI:
GitHub Actions
→ ephemeral postgres:16
→ alembic upgrade head (revision 9a0001)
→ alembic downgrade base (application schema removed)
→ alembic upgrade head
→ 34 PostgreSQL tests

Future production:
provision a PostgreSQL-compatible managed database
only beside the deployment that actually needs persistence
```

This is an intentional architecture and cost decision: do not provision standing managed databases until an actual deployment needs persistence. There is no current real production workload that justifies that recurring cost.

Verified GitHub Actions run: `32336909759`.

- Lint and test: success
- PostgreSQL integration: success

That run is ephemeral CI PostgreSQL. It is not a managed-database test.

## Rejected: shared cross-cloud database

```text
Azure Container Apps
          \
           → one DB hosted in one cloud
          /
Amazon ECS
```

Not selected as the preferred architecture. A shared cross-cloud database is possible, but it is not the design chosen here. Cross-cloud latency, data-transfer cost, asymmetric availability, outage coupling, and private-networking complexity make one cloud the persistence dependency of the other. That is a weaker multi-cloud demonstration.

## Rejected: dual standing managed databases

Phase 9 does not maintain Azure Database for PostgreSQL and Amazon RDS at the same time.

Reasons: recurring cost, no current production workload, replication/consistency complexity, and failover architecture outside project scope. Two independent databases are not automatic active-active multi-cloud. ECI does not replicate persistent data between Azure and AWS.

## Preferred future topology

Each real deployment should use a PostgreSQL database colocated with that runtime.

```text
Azure deployment (future, not provisioned in Phase 9):
Azure Container Apps
→ Azure-local PostgreSQL-compatible managed database

AWS deployment (future, not provisioned in Phase 9):
ECS Fargate
→ AWS-local PostgreSQL-compatible managed database
```

Provision only the environment actually required. The same ECI code remains portable. Databases are not assumed to synchronize. Cloud-portable application code does not mean Azure PostgreSQL and Amazon RDS have identical operational semantics.

## Future Azure path (conceptual)

```text
Azure Container Apps
→ private/controlled connectivity
→ Azure Database for PostgreSQL Flexible Server
→ PostgreSQL database
→ ECI schema
```

Later credential options:

1. secret/reference-based PostgreSQL credential
2. Microsoft Entra-based PostgreSQL authentication where practical

Entra database authentication is not implemented. Phase 16B created Azure Database for PostgreSQL Flexible Server `eci-pg-dev-susanta` (PostgreSQL 16, Burstable `Standard_B1ms`, 32 GiB, HA disabled, TLS required, schema head `13a0001`). Sequential validation must still avoid leaving Azure PG and RDS both standing indefinitely. See [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md).

## Future AWS path (conceptual)

```text
ECS Fargate
→ private/controlled connectivity
→ Amazon RDS for PostgreSQL
→ PostgreSQL database
→ ECI schema
```

Later credential options:

1. secret-managed DB credential
2. RDS IAM database authentication where operationally appropriate

IAM database authentication is not implemented. Phase 16A could not call `rds:Describe*` as `eci-developer`; the ECS task has no `DATABASE_URL`. Treat RDS as absent and required later (16D) under an explicit cost/authorization gate.

## DATABASE_URL and secrets

Current contract: environment-injected `DATABASE_URL`.

A production deployment must not permanently store a literal password in source code, GitHub, the container image, or committed configuration.

Future injection, not implemented:

- Azure: Key Vault, secret reference, or identity-based access
- AWS: Secrets Manager, task identity, or IAM-based alternatives

Phase 9D does not configure cloud `DATABASE_URL`. Current Azure Container Apps and ECS environments remain without Phase 9 database configuration. Do not deploy Phase 9 to those runtimes until a colocated database exists.

## Runtime versus migration identity

| Identity | Intended privileges |
|---|---|
| Migration | DDL / schema migration |
| Runtime application | `SELECT`, `INSERT`, `UPDATE`, `DELETE` on application schema |

Do not require the runtime app identity to own the schema in a mature production deployment. CI may use one owner user because the database is disposable.

## Migration operations

Canonical command: `alembic upgrade head`.

```text
migrate once
→ deploy app
→ readiness verification
```

Do not auto-migrate on FastAPI startup. Do not let every replica race to migrate. Do not automatically downgrade production. CI downgrade is reversibility proof on a disposable database only.

## CI PostgreSQL proof

GitHub workflow `.github/workflows/ci.yml` job `PostgreSQL integration`:

```text
postgres:16 service healthy
→ alembic upgrade head
→ revision == 9a0001
→ alembic downgrade base
→ application schema removed
→ alembic upgrade head
→ tests/postgres: 34 passed
```

Job permissions are `contents: read` only. The job does not log in to Azure or AWS. Default local pytest does not start Docker or PostgreSQL. The disposable CI database does not persist after the job. This proves PostgreSQL 16 dialect, migration round-trip, repository, uniqueness, `DELETE` rowcount, JSONB/UUID/`timestamptz`, and readiness behavior. It does not prove managed-service networking, production performance, HA, backup, PITR, or cloud IAM database authentication.

## Deferred production database concerns

Because no managed production database exists:

- managed backup and PITR
- replication
- cross-region disaster recovery
- failover / HA
- private networking, firewall, and DNS
- managed database monitoring
- connection-pool sizing against managed limits

CI PostgreSQL is not production backup, HA, or DR proof.

## Current cloud environments

Azure Container Apps `eci-api-dev` runs `eci-api:7518360` with Azure PostgreSQL `eci-pg-dev-susanta` (`DATABASE_URL` as an ACA secret). Phase 16C persisted a Graph `ConnectorAccount` (ACTIVE) and a `WorkflowAction` (PENDING → APPROVED) on that database. Schema head remains `13a0001`. No new Alembic revision. ECS service `eci-api-dev` still has no Phase 9 database configuration (16D).
