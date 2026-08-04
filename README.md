# ContextMesh

**Enterprise Communication Intelligence Platform**

ContextMesh is a production-oriented AI platform that transforms business communications into structured, actionable intelligence. The project is designed to demonstrate modern AI Solution Architecture principles through a provider-independent architecture capable of supporting multiple cloud AI providers.

Rather than being limited to email automation, ContextMesh is designed as a modular enterprise platform that can evolve to support a wide range of communication channels and business workflows.

---

## Current Status

ContextMesh is currently in active development.

Completed:

- Foundation
- Provider-independent domain model
- Provider abstraction
- Communication analysis service

Next:

- REST API
- Azure AI Foundry integration
- Amazon Bedrock integration
- Cloud deployment


## Project Goals

* Build a production-oriented AI application using clean architecture principles.
* Learn and compare **Microsoft Azure AI Foundry** and **Amazon Bedrock** using the same codebase.
* Design a provider-independent architecture where business logic remains unchanged regardless of the underlying AI provider.
* Demonstrate enterprise software engineering practices suitable for AI Solution Architect and AI Engineer roles.

---

## Current Features

* FastAPI application foundation
* Provider-independent communication domain
* Mock AI provider for offline development
* Provider factory with dependency injection
* Configuration management using Pydantic Settings
* Structured logging
* Centralized exception handling
* Health and readiness endpoints
* Comprehensive automated test suite

---

## Architecture

```
                FastAPI API
                     │
                     ▼
      Communication Analysis Service
                     │
                     ▼
              AIProvider Interface
                     │
         ┌───────────┴───────────┐
         │                       │
 MockAIProvider        Future Azure AI Foundry
                       Future Amazon Bedrock
```

The business logic is independent of cloud providers. Azure AI Foundry and Amazon Bedrock will become interchangeable implementations of the same provider interface.

---

## Project Structure

```text
app/
├── api/
├── application/
├── core/
├── domain/
├── infrastructure/
├── providers/
└── utils/

docs/
deployment/
tests/
```

---

## Technology Stack

* Python 3.12
* FastAPI
* Pydantic v2
* Pydantic Settings
* Structlog
* Pytest
* Ruff
* Docker (planned)

Future integrations:

* Microsoft Azure AI Foundry
* Amazon Bedrock
* Azure App Service
* AWS App Runner

---

## Development Roadmap

| Phase                                    | Status        |
| ---------------------------------------- | ------------- |
| Phase 1 – Foundation                     | ✅ Completed   |
| Phase 2 – Domain Model                   | ✅ Completed   |
| Phase 3 – Provider Abstraction           | ✅ Completed   |
| Phase 4 – Communication Analysis Service | ▶ In Progress |
| Phase 5 – REST API                       | ⏳ Not Started |
| Phase 6 – Azure & AWS Integration        | ⏳ Not Started |
| Phase 7 – Observability                  | ⏳ Not Started |
| Phase 8 – Future Roadmap                 | ⏳ Not Started |

---

## Running Locally

Clone the repository:

```bash
git clone https://github.com/Susanta2025-lab/contextmesh.git
cd contextmesh
```

Install dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the application:

```bash
uvicorn app.main:app --reload
```

Open:

* API Documentation: `http://localhost:8000/docs`
* OpenAPI Schema: `http://localhost:8000/openapi.json`
* Health Check: `http://localhost:8000/health`

---

## Engineering Principles

ContextMesh follows enterprise-oriented software engineering practices:

* Clean Architecture
* Separation of Concerns
* Dependency Injection
* Provider Abstraction
* Configuration Management
* Structured Logging
* Comprehensive Testing
* Cloud Portability
* Extensibility
* Maintainability

---

## Long-Term Vision

Although the initial MVP focuses on business communication analysis, the long-term vision is to evolve **ContextMesh** into a comprehensive **Enterprise Communication Intelligence Platform** that transforms scattered enterprise communications into structured, actionable intelligence.

The platform is designed to integrate with a broad ecosystem of enterprise and consumer communication systems, including:

* **Email platforms** (Gmail, Microsoft Outlook, Yahoo Mail, Microsoft Exchange, IMAP/SMTP providers)
* **Collaboration platforms** (Microsoft Teams, Slack)
* **Messaging platforms** (WhatsApp and other business messaging services)
* **CRM systems**
* **ERP systems**
* **Document repositories**
* **Calendar and scheduling systems**
* **Workflow automation platforms**

Beyond communication channels, ContextMesh is designed to support multiple AI providers, cloud platforms, and enterprise integrations through a modular, provider-independent architecture. This enables communication channels, AI providers, and deployment environments to evolve independently while preserving the core business logic, improving maintainability, scalability, and long-term extensibility.

---

## License

This project is released under the MIT License.
