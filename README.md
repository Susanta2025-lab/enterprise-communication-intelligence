<p align="center">
  <img src="frontend/public/eci-mark.svg" alt="ECI Platform logo" width="96">
</p>

<h1 align="center">Enterprise Communication Intelligence (ECI)</h1>

<p align="center">
  <strong>Register. Connect. Analyze.</strong>
</p>

**ECI** is a production-oriented enterprise AI communication platform.



It turns business communications into structured intelligence—summaries, priority, action suggestions, draft replies, and secure attachment analysis—and lets users explicitly track business actions and obligations while keeping humans in control of consequential changes and external side effects.

The same application image runs with a deterministic mock AI provider locally, **Microsoft Foundry** on Azure, and **Amazon Bedrock** on AWS. Mailbox integrations today cover **Gmail** and **Microsoft Graph / Outlook**. Application login uses **Microsoft Entra External ID** (OIDC / MSAL), separate from mailbox OAuth and from cloud workload identities.

This repository demonstrates enterprise application identity, connected mailbox workflows, AI-assisted analysis, secure attachment intelligence, controlled workflow execution, application RBAC, provider-independent AI architecture, and independent AWS and Azure deployments. It is not a claim of commercially production-ready SaaS certification or external business-user acceptance.

---

## Problem

Enterprise messages arrive across mailboxes with uneven priority, buried action items, and attachments that must not be fetched or analyzed without clear user intent. Typical automation either over-trusts AI or couples product logic to a single cloud or mailbox vendor.

ECI addresses that with:

- structured communication analysis behind a stable domain contract;
- explicit, permissioned human workflow (Propose → Approve → Execute/Send);
- fail-closed secure attachment intelligence (metadata-first; content only on explicit Analyze);
- application RBAC anchored to verified identity, not email;
- one codebase across independent Azure and AWS deployments (no cross-cloud database replication).

---

## Major capabilities

| Area | What exists today |
| --- | --- |
| Communication analysis | Summary, priority, category, action items, AI draft suggestion |
| Business context | Flat user-owned matter/case/project/client/transaction/account organization; manual communication association; context timeline; AI-assisted suggestions with human confirmation (never autonomous assignment) |
| Tracking / Work Items | Durable user-confirmed actions and obligations; optional Business Context and due value; lifecycle, archive/restore, verified provenance and auditable event history; Tracking list/detail UI and Context workspace integration |
| Mailboxes | Gmail and Microsoft Graph/Outlook: connect, list, selected-message analyze |
| Secure attachments | Metadata listing; explicit single-attachment Analyze for PDF / DOCX / TXT / XLSX; JPEG/PNG gated when image AI is unavailable; legacy spreadsheet formats unsupported |
| Workflow | Explicit Propose / Approve / Reject / Execute (Send)—never automatic from analyze, attachment analysis, or context suggestion |
| Application auth | Microsoft Entra External ID + MSAL; five delegated `communications:*` scopes |
| Application RBAC | Persisted `application_role` (`user` \| `owner`); server-side `require_owner`; `/api/v1/me` and owner-only `/api/v1/admin/ping` |
| AI providers | `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider` |
| Hosting | Azure Container Apps + Static Web Apps; AWS ECS Fargate + CloudFront/S3/ALB |
| Persistence | PostgreSQL (user-owned analyses, workflow actions, attachment analyses, business contexts, work items with sources and events); separate DB per cloud |
| Credential stores | Azure Key Vault / AWS Secrets Manager (opaque `credential_ref`; no tokens in PostgreSQL) |
| Malware scanning | ClamAV client → external clamd (not embedded in the API image); production fails closed without a real scanner |

**Phase 18 invariant:** ECI never explicitly retrieves, decodes, persists, or analyzes attachment content without an explicit user action for that specific attachment. There is no automatic attachment download. Listing remains content-free. Raw attachment bytes are not durably persisted. ClamAV runs before parsing or AI. Unsupported or dangerous cases fail closed. Attachment analysis cannot trigger Propose, Approve, Execute, or Send. Context open / timeline / association / AI suggestion never retrieve attachment bytes.

**Phase 21 XLSX support:** `.xlsx` only; `.xls`, `.xlsm`, `.xlsb`, `.csv`, and `.tsv` remain unsupported. Explicit Analyze checks ownership/provenance, retrieves one attachment, and requires a CLEAN scanner verdict before container validation and bounded `openpyxl` extraction. Formulas remain inert; external relationships, workbook links, macros, and connections are rejected. No raw workbook is persisted. Complete validated advisory `tabular_result` is stored in existing attachment history; potential dates, amounts, and actions do not create business state. Azure/Outlook/Foundry and AWS/Gmail/Bedrock deployment and functional validation passed, as manually reported by the operator on 2026-09-23; Phase 21 is CLOSED for the delivered XLSX scope. Live evidence limits are recorded in the [Phase 21G report](docs/codex/reports/phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See the [Phase 21 roadmap](docs/roadmap/phase-21-xlsx-tabular-intelligence.md).

**Phase 22 Tracking:** A Work Item records a business action to carry out or an obligation the user has chosen to track. It is distinct from an advisory AI action suggestion and from a reply workflow. Completion records a human declaration, not independent proof of fulfillment.

- Create manually without a connected mailbox, or explicitly review and confirm a candidate from a persisted communication or attachment analysis, including XLSX observations. AI never silently creates work items or confirms deadlines.
- Track `open`, `in_progress`, `completed` and `cancelled` status, explicitly reopen terminal items, and archive/restore independently of status. Versioned optimistic concurrency rejects stale edits; creation keys support safe replay.
- Choose no due value, a calendar date, or a precise time with a confirmed IANA timezone. Overdue is computed for active, unarchived items; no reminders, scheduler or automatic lifecycle changes are included.
- Retain bounded, verified source references and append-only event history through normal application operations. Tracking reads do not retrieve mailbox or attachment content, invoke AI, or send communications.
- Filter and page the Tracking list, review detail/history, and optionally associate one owned Business Context. Contexts provide a Tracking tab and genuine historical events; current association and historical context membership remain distinct.

See [ADR-030](docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md) for the architecture contract and the [Phase 22E report](docs/codex/reports/phase_22e_report.md) for UI and Context integration evidence.

**Not yet productized:** reminders/escalations; shared assignment; DMS/CRM/case-system sync; autonomous context assignment.

---

## Architecture (high level)

```mermaid
flowchart TB
  subgraph clients [Clients]
    SPA[React SPA / MSAL]
  end

  subgraph api [API]
    FastAPI[FastAPI REST API]
  end

  subgraph app [Application]
    Analysis[Communication analysis]
    Mailbox[Mailbox list / analyze]
    Attach[Attachment analyze]
    Context[Business context / timeline / suggest]
    Tracking[Work items / due values / event history]
    Workflow[Workflow propose / approve / execute]
    RBAC[Identity mapping / application RBAC]
  end

  subgraph domain [Domain]
    Ports[AIProvider / Connector / Scanner ports]
  end

  subgraph providers [Providers and adapters]
    Mock[Mock AI]
    Foundry[Microsoft Foundry]
    Bedrock[Amazon Bedrock]
    Gmail[Gmail connector]
    Graph[Microsoft Graph connector]
    ClamAV[ClamAV scanner client]
  end

  subgraph data [Data and secrets]
    PG[(PostgreSQL)]
    KV[Azure Key Vault / AWS Secrets Manager]
  end

  SPA --> FastAPI
  FastAPI --> Analysis
  FastAPI --> Mailbox
  FastAPI --> Attach
  FastAPI --> Context
  FastAPI --> Tracking
  FastAPI --> Workflow
  FastAPI --> RBAC
  Analysis --> Ports
  Mailbox --> Ports
  Attach --> Ports
  Context --> Ports
  Workflow --> Ports
  Ports --> Mock
  Ports --> Foundry
  Ports --> Bedrock
  Ports --> Gmail
  Ports --> Graph
  Ports --> ClamAV
  Analysis --> PG
  Attach --> PG
  Context --> PG
  Tracking --> PG
  Workflow --> PG
  RBAC --> PG
  Gmail --> KV
  Graph --> KV
```

Dependency direction stays:

**API → Application → Domain → Interfaces → Providers / Infrastructure**

Domain code does not depend on FastAPI, Azure SDK, AWS SDK, or HTTP clients. Cloud SDKs stay inside provider and infrastructure adapters.

AI provider pattern (application/domain boundary is cloud-neutral; infrastructure adapters are not interchangeable):

```text
ECI application / service layer
             ↓
       AI provider contract
          ↙        ↘
    Microsoft      Amazon
     Foundry        Bedrock
```

---

## Identity model

**ECI application login ≠ mailbox login.**

| Identity class | What it is | What it is not |
| --- | --- | --- |
| Application identity | Entra External ID OIDC → verified `(issuer, subject)` → `users.id` → persisted `application_role` | Does not grant mailbox access |
| Mailbox identity | Separate Gmail / Microsoft Graph delegated OAuth → credential store | Does not determine Platform Owner |
| Workload identity | Azure Managed Identity / AWS ECS Task Role | Not an end-user login |
| Database identity | PostgreSQL roles/credentials | Not application RBAC |
| Deploy identity | GitHub OIDC → Azure UAMI / AWS IAM deploy role | Not runtime product login |

Authorization for Platform Owner is:

```text
verified (issuer, subject)
        ↓
external identity mapping
        ↓
internal users.id
        ↓
persisted application_role
```

Email may appear in the UI for display, but it is **not** the authorization key. New or mapped users remain ordinary `user` unless explicitly promoted. Owner checks use server-side persistence—not a frontend badge or client-supplied role.

First-owner bootstrap uses the operator CLI with an **internal user UUID** (the target must already have an external identity mapping). A conflicting second-owner bootstrap is refused:

```bash
python -m app.cli.promote_owner --user-id <internal-user-uuid>
```

Do not put live internal user UUIDs or owner emails into documentation examples.

---

## Multi-cloud design

The same application, domain, and API are intentionally cloud-neutral. **Azure and AWS deployments are independent.** There is **no** cross-cloud database replication—each cloud has its own PostgreSQL and cloud resources.

### Azure

```text
Azure Static Web Apps
        ↓
Azure Container Apps
        ↓
Azure Database for PostgreSQL Flexible Server
        ↓
Microsoft Foundry (GPT-5.4-mini)
```

Supporting services include Azure Key Vault, managed identity, and Log Analytics. Region: **Spain Central**.

### AWS

```text
S3 + CloudFront (SPA)
        ↓
CloudFront API distribution
        ↓
Application Load Balancer
        ↓
ECS Fargate
        ↓
RDS PostgreSQL
        ↓
Amazon Bedrock (Claude Haiku 4.5)
```

Supporting services include AWS Secrets Manager, ECS Task Role, and CloudWatch. Region: **eu-south-2**.

Detailed comparison: [docs/cloud/comparison.md](docs/cloud/comparison.md).

Do not treat AI latency differences between Azure and AWS as a pure cloud-performance comparison—model and provider differences also matter. Neutral cloud presentation in the UI is not an official Microsoft or AWS endorsement.

---

## Platform Owner deployment indicator

Authenticated Platform Owners see an owner-visible deployment presentation indicator alongside the Platform Owner badge (for example **Platform Owner** with **Azure** or **AWS**). Expanded presentation may show safe labels such as:

| Cloud | AI | Region |
| --- | --- | --- |
| Azure | Microsoft Foundry | Spain Central |
| AWS | Amazon Bedrock | eu-south-2 |

This metadata is **presentation only**. It has no authorization significance, must not determine owner access, must not replace server-side RBAC, and must not expose infrastructure secrets or private identifiers.

---

## Frontend cloud builds

Manual cloud-specific Vite builds avoid accidental cross-environment configuration leakage:

```bash
# Azure
cd frontend
npm run build:azure
# equivalent: npm run build -- --mode azure

# AWS
npm run build:aws
# equivalent: npm run build -- --mode aws
```

Do **not** use a generic `npm run build` as the manual Azure or AWS deployment command.

Configuration model:

- **Azure:** tracked `frontend/.env.azure` contains **public presentation metadata only**. Operator/auth/API values remain local, environment, or CI supplied (for example `.env.azure.local`).
- **AWS:** tracked `frontend/.env.aws` contains **public presentation metadata only**. Operator/auth/API values remain local, environment, or CI supplied (for example `.env.aws.local`).

`.env.local` is shared across Vite modes; use `.env.azure.local` and `.env.aws.local` for mode-specific operator values.

Never place secrets, tokens, or client secrets in frontend env files. Presentation metadata has no authorization significance.

---

## Security and privacy design

- Fail-closed production auth (`APP_ENV=production` requires `AUTH_MODE=oidc`).
- Distinct permissions: `communications:read`, `analyze`, `connect`, `workflow`, `send`.
- Application RBAC (`user` / `owner`) is separate from mailbox OAuth and from `communications:*` scopes.
- Business Context and Work Item ownership is server-authoritative, keyed to internal `users.id`; Platform Owner does not bypass object ownership.
- AI suggestions remain advisory. Tracking creation/confirmation and lifecycle changes require explicit user action and never bypass Analyze → Propose → Approve/Reject → Execute for replies.
- Raw message bodies and raw attachment bytes are not durable product storage for analysis history.
- Attachment path: explicit user action → retrieve one → ClamAV → parse → AI; unsupported / dangerous cases fail closed.
- Privacy-safe operational logs (no tokens, secrets, or sensitive message/attachment bodies).
- Mailbox credentials outside PostgreSQL (Key Vault / Secrets Manager + advisory-lock coordination).

---

## Technical cloud validation status

Technical deployments have been validated on both clouds. This is **technical deployment validation**, not Phase 17D external business-user acceptance.

| Cloud | Validated (technical) |
| --- | --- |
| **AWS** | Frontend and backend operational; persistence during validation; application identity; first Platform Owner activation; `/api/v1/me`; owner-only `/api/v1/admin/ping`; owner deployment indicator shows AWS |
| **Azure** | Frontend operational; `/health` and `/api/v1/readiness`; PostgreSQL persistence during runtime check; application sign-in; `/api/v1/me`-backed owner state in UI; owner deployment indicator shows Azure; existing connected-mailbox state loads |

**Phase 22:** AWS backend, controlled synthetic lifecycle, frontend and scoped browser validation completed ([AWS evidence and limits](docs/codex/reports/phase_22g_report.md)). Azure backend/migration, controlled synthetic lifecycle, frontend and scoped browser validation also completed ([operator-observed Azure evidence](docs/codex/reports/phase_22h_azure_readiness_report.md#closure-addendum--2026-10-02)). Azure checks covered health/readiness, real Entra/MSAL `/me`, Tracking detail/history and reload, Contexts loading, and successful authenticated API/CORS requests. AWS and Azure evidence remain separate; neither establishes exhaustive live acceptance coverage.

Phase 18 also live-validated secure attachment intelligence on crossed paths (Outlook → Azure / Foundry; Gmail → AWS / Bedrock) without Send. Image analysis is not live-supported today (adapters report image input unavailable; JPEG/PNG gated before retrieval).

Development and demo cloud resources may be intentionally stopped when not in use to control cost. Meaningful live testing requires an active serving revision (Azure Container App) or running ECS service, and an available PostgreSQL instance on that cloud.

---

## Testing and quality evidence

The repository includes automated backend and frontend test coverage (offline, deterministic). GitHub Actions CI runs pip check, ruff, pytest, ephemeral PostgreSQL integration, and frontend jobs.

Phase closures record live validation separately from offline regression. Live proofs use owner-controlled paths and stop before Send unless a phase explicitly records otherwise (Phase 16E historically included one manual Gmail Send; Phase 18 did not Send).

---

## Current project status

### Implemented through Phase 22

Phases **1–16** are completed (foundation through cloud-hosted browser and multi-cloud mailbox→AI validation).

**Phase 17 — Microsoft Entra External ID**

- **17A–17C:** CLOSED / PASS (External ID product login, controlled validation, Gmail ID-token clock-skew hardening).
- **17D** external business-user verification: **DEFERRED / OUT OF CURRENT RELEASE SCOPE**.

**Phase 18 — Secure Attachment Intelligence:** **Completed / PASS**.

**Phase 19 — Platform Owner Identity & Application RBAC:** **Completed / PASS** (schema `19b0001`, server-side owner authorization, bootstrap CLI, `/me`, owner-aware UI). Follow-up technical deployment validation exercised first Platform Owner activation and the owner deployment indicator on AWS and Azure.

**Phase 20 — Business Context & Matter Intelligence:** **CLOSED / PASS**.

**Phase 21 — XLSX / Tabular Intelligence:** **CLOSED / PASS** for the delivered XLSX scope.

**Phase 22 — Action, Deadline & Obligation Tracking:** **Implemented and validated** through local regression and scoped AWS/Azure deployment, lifecycle and frontend acceptance. PostgreSQL migration `22b0001` adds work items, sources and events. See [local hardening evidence](docs/codex/reports/phase_22f_report.md) and the cloud validation summary above. Source committed and pushed to `master` as `46128f2`; push CI passed (run `36846483687`). The [dated closure status](docs/roadmap/phase-22-action-deadline-obligation-tracking.md#closure-status-addendum--2026-10-02) records the full commit SHA and separate evidence categories while preserving historical readiness statements. Remaining live coverage limits in the AWS report are not claimed as passed.

External business-user verification remains deferred and outside the currently completed release scope.

### Realistic remaining work

- Phase 17D external business-user verification (deferred).
- Optional: authorized live EICAR-vs-ClamAV; multimodal enablement only after a proven image-capable adapter.
- Mailbox sync, search, bulk analysis, workers, webhooks.
- Automatic replies, retry/reconciliation, exactly-once delivery.
- Full 2×2×2 cloud × mailbox × AI matrix (validated crossed paths only).
- Distributed tracing, custom metrics/dashboards/alerts, DB backup/PITR/HA/DR hardening.

Stopped managed databases may automatically restart after the provider stop interval (AWS currently 7 days). Privileged RDS / Azure PostgreSQL start-stop remains an operator action.

---

## Repository structure

```text
app/                 FastAPI API, application, domain, infrastructure, providers
frontend/            React + TypeScript + Vite SPA (MSAL)
tests/               Unit, integration, provider, PostgreSQL suites
deployment/
  azure/             ACA / SWA / Key Vault operator runbook
  aws/               ECS / CloudFront / RDS / Secrets Manager runbook
  docker/            Shared image build context
docs/
  architecture/      Layering and design
  decisions/         ADRs
  cloud/             Foundry, Bedrock, auth, deployment, observability
  api/               REST API reference
  diagrams/          Mermaid sources
  roadmap/           Phase history and closures
```

---

## Local development (quick start)

**Backend**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env   # set AI_PROVIDER=mock for offline work
uvicorn app.main:app --reload
```

**Frontend** (`frontend/`)

```bash
cp .env.example .env   # public External ID / MSAL SPA values only
npm install
npm run dev            # http://localhost:5173
```

Set `CORS_ALLOWED_ORIGINS=http://localhost:5173` on the API. Configure mailbox OAuth client ids/redirects per `.env.example` when exercising connectors. Prefer `CREDENTIAL_STORE_BACKEND=memory` only for local/dev; production rejects `memory`.

Application login alone does not authorize a mailbox—mailbox testing requires an explicit separate OAuth operation. Prefer an ordinary application `user` for external evaluation; do not share the Platform Owner account with reviewers. AI execution and attachment retrieval may incur provider cost; Send/workflow execution should remain separately controlled.

**Quality checks**

```bash
python -m pip check
python -m ruff check .
python -m pytest
cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run build
```

---

## Technology stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL
- **Frontend:** React 19, TypeScript, Vite, MSAL, TanStack Query, Tailwind CSS
- **AI:** Provider abstraction; Mock; Microsoft Foundry (Responses API); Amazon Bedrock (Converse)
- **Cloud:** Azure Container Apps, ACR, Key Vault, Static Web Apps, Log Analytics; AWS ECS Fargate, ECR, Secrets Manager, CloudWatch, CloudFront, S3, ALB, RDS
- **CI/CD:** GitHub Actions + GitHub OIDC (no long-lived deploy secrets in the app image)

---

## Documentation map

| Topic | Link |
| --- | --- |
| Roadmap index | [docs/roadmap/README.md](docs/roadmap/README.md) |
| Phase 22 (closure status and original plan) | [docs/roadmap/phase-22-action-deadline-obligation-tracking.md](docs/roadmap/phase-22-action-deadline-obligation-tracking.md) |
| Phase 22 local validation | [docs/codex/reports/phase_22f_report.md](docs/codex/reports/phase_22f_report.md) |
| Phase 22 AWS validation | [docs/codex/reports/phase_22g_report.md](docs/codex/reports/phase_22g_report.md) |
| Phase 22 Azure completion and historical readiness / rollback baseline | [docs/codex/reports/phase_22h_azure_readiness_report.md](docs/codex/reports/phase_22h_azure_readiness_report.md) |
| Phase 19 (RBAC / owner) | [docs/roadmap/phase-19-platform-owner-identity-and-application-rbac.md](docs/roadmap/phase-19-platform-owner-identity-and-application-rbac.md) |
| Phase 18 (attachments) | [docs/roadmap/phase-18-secure-attachment-intelligence.md](docs/roadmap/phase-18-secure-attachment-intelligence.md) |
| Phase 17 (External ID) | [docs/roadmap/phase-17-external-id-external-user-onboarding.md](docs/roadmap/phase-17-external-id-external-user-onboarding.md) |
| Architecture | [docs/architecture/README.md](docs/architecture/README.md) |
| ADRs | [docs/decisions/README.md](docs/decisions/README.md) |
| Cloud / AI providers | [docs/cloud/README.md](docs/cloud/README.md) |
| Cloud comparison | [docs/cloud/comparison.md](docs/cloud/comparison.md) |
| Authentication | [docs/cloud/authentication.md](docs/cloud/authentication.md) |
| API | [docs/api/README.md](docs/api/README.md) |
| Diagrams | [docs/diagrams/README.md](docs/diagrams/README.md) |
| Azure runbook | [deployment/azure/README.md](deployment/azure/README.md) |
| AWS runbook | [deployment/aws/README.md](deployment/aws/README.md) |
| Frontend | [frontend/README.md](frontend/README.md) |

---

## Development roadmap (summary)

| Phase | Status |
| --- | --- |
| Phases 1–16 | Completed |
| Phase 17 – External ID & external user onboarding | 17A–17C CLOSED / PASS; **17D deferred** |
| Phase 18 – Secure Attachment Intelligence | **Completed / PASS** |
| Phase 19 – Platform Owner Identity & Application RBAC | **Completed / PASS** |
| Phase 20 – Business Context & Matter Intelligence | **CLOSED / PASS** — see roadmap for recorded live validation |
| Phase 21 – XLSX / Tabular Intelligence | **CLOSED — 21A–21G PASS**; Azure/AWS manual live validation complete; evidence limits in the Phase 21G report |
| Phase 22 – Action, Deadline & Obligation Tracking | **Implemented and validated**; local regression and separate scoped AWS/Azure cloud validation complete; committed/pushed to `master` (`46128f2`), CI PASS; live evidence limits retained |

Full phase table and narratives: [docs/roadmap/README.md](docs/roadmap/README.md).

---

## License

MIT License
