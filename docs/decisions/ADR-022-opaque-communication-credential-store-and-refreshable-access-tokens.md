# ADR-022: Opaque Communication Credential Store and Refreshable Access Tokens

## Status

Accepted

The decision is implemented for Phase 13B. The provider-neutral credential store, server-generated locators, and refreshable `AccessTokenProvider` foundation exist. Phase 13C/13D added Google and Microsoft OAuth. Phase 13E added Azure Key Vault and AWS Secrets Manager backends. Phase 13E live Azure Key Vault and AWS Secrets Manager store validation is recorded below. Azure Key Vault itself does not supply atomic CAS.

## Date

Phase 13 (Production Mailbox OAuth)

## Context

Phase 12 executes approved mailbox replies using `CommunicationCredentialResolver.resolve(credential_ref, provider) -> AccessTokenProvider`. `AccessTokenProvider` remains `Callable[[], str]`. Resolution is side-effect-free with respect to secret lookup; token material is retrieved only when the callable is invoked. That preserves the Phase 12 execution boundary:

```text
TX1 APPROVED → EXECUTING
→ commit / close UoW
→ invoke AccessTokenProvider
→ provider I/O
→ TX2 EXECUTED | FAILED | uncertain EXECUTING
```

Phase 12B's environment-backed resolver is valid for local/dev and legacy tests. It is not a production refreshable mailbox credential. Production credentials must not live in PostgreSQL, must not be unique-indexed on `ConnectorAccount.credential_ref` (environment locators such as `demo-account` may be reused), and must rotate safely across multiple ACA/ECS instances.

## Decision

Mailbox secrets are stored behind a provider-neutral `CommunicationCredentialStore`. `ConnectorAccount` continues to store only an opaque `credential_ref` locator.

```text
ConnectorAccount.credential_ref
        ↓
CommunicationCredentialResolver.resolve(...)
        ↓
AccessTokenProvider
        ↓
on invocation only:
CommunicationCredentialStore
        ↓
provider-neutral refresh adapter
        ↓
valid access token
        ↓
optional rotated credential material
        ↓
compare-and-set secret replacement
        ↓
short-lived in-process access-token cache
```

Durable rules:

- Credential secrets are outside relational persistence. No access token, refresh material, OAuth cache, client secret, or authorization code columns are added to `ConnectorAccount`, `CommunicationActionExecution`, or `WorkflowAction`.
- `CommunicationCredentialStore` is a SQLAlchemy-free, cloud-SDK-free port: `create`, `get`, `replace_if_version`, `delete`.
- Stored material is an opaque serialized payload plus only common metadata (`credential_ref`, `provider`, opaque `version`). Google-specific and Microsoft-specific fields are not part of the port.
- Version is an opaque string suitable for in-memory tests and future Azure Key Vault / AWS Secrets Manager backends. The application treats version as opaque.
- `create` fails if the locator already exists. `replace_if_version` is compare-and-set and must not blindly overwrite. `delete` of an unknown well-formed locator is a no-op.
- Locators are server-generated (`oauth-` plus high-entropy hex), compatible with `^[A-Za-z][A-Za-z0-9-]{0,62}$`, never derived from user id/email/provider account id, and never accepted from public clients. Collision handling generates a new locator and retries a bounded number of times. Exhausted collisions fail closed. There is no database unique constraint on `connector_accounts.credential_ref`.
- `OAuthCommunicationCredentialResolver` implements `CommunicationCredentialResolver`. `resolve()` performs no secret-store lookup, token refresh, or provider HTTP. Those happen only when the returned callable is invoked.
- Provider adapters are injected (`RefreshableCredentialAdapter`). Unsupported provider, missing adapter, and store/request provider mismatch fail closed. Aliases are not accepted. Supported mailbox providers remain `gmail` and `microsoft_graph`.
- A bounded in-process access-token cache is keyed by `(provider, credential_ref)` and stores token plus expiration. A cached token is usable only when it remains valid beyond a 5-minute refresh skew. Cache entries are never persisted.
- Concurrent callers for the same credential share a per-key in-process lock so one process does not duplicate refresh work. Unrelated credentials are not serialized behind one global lock. Locks are refcounted and removed when idle. In-process locks are not a multi-instance safety mechanism.
- Multi-instance rotation safety is compare-and-set on the store version. If CAS loses, the caller re-reads the winner and retries acquisition once. Stale replacements are never written. Retry is bounded. There is no Redis, distributed lock, database lease, or queue worker in 13B.
- Phase 13E correction: Azure Key Vault Set Secret is not a linearizable compare-and-swap. Durable cloud backends therefore serialize create / replace_if_version / delete with PostgreSQL transaction-scoped `pg_advisory_xact_lock`, keyed deterministically by a SHA-256 digest of a fixed ECI namespace plus the opaque `credential_ref`. Same-locator create / replace / delete serialize across ECI instances that share the same PostgreSQL database. The database is a coordination mechanism only; no OAuth secret or token material is stored in PostgreSQL. The mutation transaction holds one database connection during the infrequent cloud control-plane write. AWS retains native version/stage compare-and-set in addition to this coordination. The in-memory development store is unchanged and does not require PostgreSQL. Durable cloud backends fail closed if PostgreSQL coordination cannot be constructed. `get()` remains lock-free.
- Same-process cache invalidation is wired through store mutation listeners: delete or replace of a locator drops cached tokens for that locator. Cross-instance cache invalidation is not provided; access tokens remain short-lived and CAS protects secret material.
- `AccessTokenProvider` is unchanged. Phase 12 execution classes and Gmail/Graph executor semantics are unchanged. There is no automatic provider-send retry and no workflow reconciliation.
- Token resolution does not mutate `ConnectorAccount`. `CommunicationCredentialReauthorizationRequiredError` is a typed subclass of `CommunicationCredentialUnavailableError` so existing executors still observe unavailable/uncertain behavior after TX1. Automatic `ACTIVE` → `REAUTH_REQUIRED` is later credential-lifecycle work.
- `EnvironmentCommunicationCredentialResolver` remains the local/dev/legacy execute composition. The refreshable resolver is available through an explicit construction hook. It is not the production runtime default in 13B because real Google/Microsoft credentials and cloud secret backends do not yet exist.
- Provider adapters arrive in 13C/13D. Key Vault and Secrets Manager arrive in 13E.

## Alternatives Considered

- **Persist mailbox secrets in PostgreSQL** — rejected. Relational rows are not a secret store and would couple OAuth material to backups, replicas, and application queries.
- **Unique index on `credential_ref`** — rejected. Phase 12 environment-backed accounts may reuse locators. Collision checks belong to the credential store.
- **Move secret/token I/O into `resolve()` / TX1** — rejected. That would hold the execution unit of work across secret-store and token-endpoint I/O.
- **Integer-only secret versions** — rejected. Future Key Vault and Secrets Manager versions are opaque strings.
- **Distributed cache or lock (Redis)** — rejected in 13B as the primary CAS mechanism. Phase 13E does not introduce Redis. PostgreSQL advisory locks serialize cloud credential mutations because Azure Key Vault cannot implement the store CAS contract alone. PostgreSQL is already the application database and stores no OAuth secrets.
- **Make the OAuth resolver the production default in 13B** — rejected. No real provider adapters or production secret backend exist yet. Environment-backed execute remains valid.
- **Google or Microsoft fields on the store port** — rejected. The store must hold either provider's serialized material without redesign.

## Consequences

- 13C/13D can persist refreshable credential material under a server-generated locator and later plug provider adapters into the existing resolver.
- 13E can implement `CommunicationCredentialStore` with Key Vault or Secrets Manager without changing `AccessTokenProvider` or Phase 12 execution.
- Operators must not treat 13B as production mailbox OAuth. Environment tokens remain the current execute path.
- Same-process cache invalidation depends on composing the in-memory store (or a future store wrapper) with the resolver. Cross-instance stale access tokens expire by skew; secret rotation remains CAS-safe.

## Benefits

- Phase 12 TX1 stays free of secret and token I/O.
- Rotation is safe across multiple application instances. Durable cloud backends obtain that safety from compare-and-set plus PostgreSQL advisory-lock serialization; Key Vault itself does not provide CAS.
- Provider SDKs and cloud secret SDKs stay out of domain and application code.

## Trade-offs

- In-process token cache is not coherent across replicas. That is accepted because access tokens are short-lived and secret material uses CAS.
- 13B cannot live-certify Google or Microsoft token refresh.
- A permanently invalid refresh credential still surfaces as unavailable/uncertain execution until later lifecycle work maps it onto `REAUTH_REQUIRED`.

## Validation

Phase 13E PostgreSQL coordination tests (with `ECI_POSTGRES_TEST_DATABASE_URL` enabled):

- `tests/postgres/test_credential_mutation_coordination.py`: 4 passed
- complete `tests/postgres` suite: 70 passed
- complete suite: 1720 passed, 0 skipped

Azure live store validation used existing development Key Vault `eci-kv-oauth-dev-susanta` (Spain Central, RBAC authorization enabled) through factory → PostgreSQL advisory coordinator → `AzureKeyVaultCommunicationCredentialStore` → `DefaultAzureCredential` → Azure Key Vault. Create, get, normal version replacement, stale-version rejection, coordinated delete, and synthetic-probe cleanup passed. Two independently constructed stores racing the same expected version produced exactly one winner and one loser; winning material remained persisted. This does not mean Azure Key Vault itself provides linearizable CAS.

AWS live store validation used the existing ECI developer identity in `eu-south-2` through factory → PostgreSQL advisory coordinator → `AwsSecretsManagerCommunicationCredentialStore` → boto3/default AWS authentication → AWS Secrets Manager. Create, get, normal version replacement, and delete (existing 7-day recovery window) passed. The same independent-store race produced exactly one winner and one loser; winning material remained persisted. Scheduled-for-deletion `GetSecretValue` maps to provider-neutral absence (`None`) after `DescribeSecret` confirms `DeletedDate`. Required IAM on `eci/mailbox-oauth/*` is `CreateSecret`, `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `DeleteSecret`, and `DescribeSecret`. `ListSecrets` is not required. `SecretsManagerFullAccess` is not recommended.

Final code verification: `python -m pip check` passed; `python -m ruff check .` passed; full pytest with PostgreSQL integration enabled: 1720 passed.

## Related Components

- `app/domain/interfaces/communication_credential_store.py`
- `app/domain/interfaces/communication_credential_resolver.py`
- `app/infrastructure/credentials/memory.py`
- `app/infrastructure/credentials/oauth.py`
- `app/infrastructure/credentials/locators.py`
- `app/infrastructure/credentials/refresh.py`
- `app/infrastructure/credentials/azure_key_vault.py`
- `app/infrastructure/credentials/aws_secrets_manager.py`
- `app/infrastructure/credentials/mutation.py`
- `app/infrastructure/storage/credential_mutation.py`
- [ADR-019](ADR-019-production-communication-write-architecture.md)
- [ADR-020](ADR-020-uncertain-communication-execution-semantics.md)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
