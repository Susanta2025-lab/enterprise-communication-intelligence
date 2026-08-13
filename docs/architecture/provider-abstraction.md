# Provider Abstraction

This documents the provider abstraction as actually implemented: `app/domain/interfaces/ai_provider.py`, `app/providers/mock/provider.py`, `app/providers/microsoft_foundry/provider.py`, `app/providers/factory.py`, and their wiring into `app/api/dependencies.py`.

## `AIProvider` (`app/domain/interfaces/ai_provider.py`)

A single abstract method defines the entire contract:

```python
class AIProvider(ABC):
    @abstractmethod
    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication and return structured business results."""
```

The interface lives in `app/domain`, not `app/providers`, so it can be depended on by both the application layer and any provider implementation without creating a dependency on a specific provider. It exposes and accepts only domain types (`CommunicationRequest`, `CommunicationAnalysisResult`) — no Azure or AWS concepts leak through it.

## `MockAIProvider` (`app/providers/mock/provider.py`)

Deterministic offline provider for local development and tests. It is:

- **Deterministic** — identical input always produces identical output (verified by `test_mock_provider_is_deterministic`).
- **Offline** — no network calls, no randomness, no cloud SDK usage.
- **Rule-based**, using simple keyword matching on the message subject and body:
  - Critical/emergency keywords → `PriorityLevel.CRITICAL`
  - Urgent keywords (`urgent`, `asap`, `immediately`, `critical`, `emergency`) → `PriorityLevel.HIGH`
  - Promotional keywords (`unsubscribe`, `discount`, `sale`, `promotion`, `newsletter`, `offer`) → `PriorityLevel.LOW`
  - Action-oriented keywords (`meeting`, `deadline`, `please review`, `action required`, `follow up`, `schedule`, `by friday`, `by tomorrow`) → `PriorityLevel.HIGH`, and one `ActionItem` is generated
  - Otherwise → `PriorityLevel.MEDIUM`
  - Category classification uses a similar keyword lookup for `incident`, `approval`, `notification`, `inquiry`, `request`, or `general`
  - A draft reply is generated (unless `include_draft_reply=False`) with wording that depends on the assigned priority level

It sets `provider="mock"` (via `MockAIProvider.PROVIDER_NAME`) on every `CommunicationAnalysisResult` it returns.

This logic is intentionally simple test/development infrastructure — it is not, and is not meant to be, a real language model.

## `MicrosoftFoundryProvider` (`app/providers/microsoft_foundry/provider.py`)

Cloud adapter for Microsoft Foundry. It implements the same `AIProvider` contract and returns `provider="microsoft_foundry"`.

```text
DefaultAzureCredential
        ↓
AIProjectClient
        ↓
get_openai_client()
        ↓
responses.create(...)
```

Key properties:

- Authenticates with Microsoft Entra ID via `DefaultAzureCredential` (Azure CLI locally; Managed Identity in a future Azure deployment).
- Uses the Foundry project endpoint and deployment name from settings.
- Requests strict JSON Schema structured output from the Responses API, validates it, and maps it onto existing domain models.
- Honors `include_action_items` and `include_draft_reply`.
- Keeps Azure SDK types inside the provider package.
- Does not use API-key authentication.

See [Microsoft Foundry](../cloud/azure-ai-foundry.md) and [ADR-006](../decisions/ADR-006-azure-ai-foundry.md).

## Provider Factory (`app/providers/factory.py`)

```python
def create_ai_provider(settings: Settings | None = None) -> AIProvider:
    resolved = settings or get_settings()
    provider_name = resolved.ai_provider.strip().lower()
    if provider_name == "mock":
        from app.providers.mock.provider import MockAIProvider
        return MockAIProvider()
    if provider_name == "microsoft_foundry":
        from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
        return MicrosoftFoundryProvider(...)
    raise ConfigurationError(
        f"Unsupported AI provider '{resolved.ai_provider}'. "
        "Supported providers: mock, microsoft_foundry"
    )
```

Key properties:

- **Configuration-driven selection.** The provider is chosen entirely by `Settings.ai_provider` (backed by the `AI_PROVIDER` environment variable, normalized to lowercase).
- **Localized imports.** Concrete provider imports happen inside each branch, so selecting `mock` does not construct Foundry clients.
- **No global registry.** There is no module-level dict or singleton mapping provider names to classes; the factory is a plain function with an explicit `if`/`raise` structure.

## Dependency Injection

`app/api/dependencies.py`:

```python
def get_ai_provider() -> AIProvider:
    return create_ai_provider(get_settings())

def get_communication_analysis_service(
    provider: AIProvider = Depends(get_ai_provider),
) -> CommunicationAnalysisService:
    return CommunicationAnalysisService(provider)
```

FastAPI resolves `get_ai_provider` as a dependency of `get_communication_analysis_service`, which is itself injected into the `POST /api/v1/communications/analyze` route. This is the only place `fastapi.Depends` is combined with provider resolution — the factory function itself has no FastAPI dependency. The API layer never imports `MicrosoftFoundryProvider` or `MockAIProvider` directly.

## Explicit Failure for Unsupported Providers

If `AI_PROVIDER` is set to anything other than `mock` or `microsoft_foundry` (e.g. `azure`, `aws`, `openai`), `create_ai_provider` raises `ConfigurationError` immediately. There is no `try`/`except` around the lookup that would swallow the error, and no default case that returns `MockAIProvider()`.

## Why No Silent Fallback Is Allowed

A silent fallback to `MockAIProvider` when an unsupported provider is configured would mean:

- Production misconfiguration (e.g. a typo in `AI_PROVIDER`) would silently serve deterministic mock analysis instead of failing loudly.
- Operators would have no signal that the intended provider was never actually selected.

Failing explicitly with `ConfigurationError` — which is translated into an HTTP `500` by the exception handler in `app/main.py` — surfaces misconfiguration immediately instead of masking it.

## AWS: Future Adapter Only

Amazon Bedrock is not implemented. When added, it should implement `AIProvider` in its own package and gain one factory branch, keeping AWS SDK imports confined to that package.
