# Provider Abstraction

This documents the provider abstraction as actually implemented: `app/domain/interfaces/ai_provider.py`, `app/providers/mock/provider.py`, `app/providers/factory.py`, and their wiring into `app/api/dependencies.py`.

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

The only implemented provider. It is:

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

## Provider Factory (`app/providers/factory.py`)

```python
def create_ai_provider(settings: Settings | None = None) -> AIProvider:
    resolved = settings or get_settings()
    provider_name = resolved.ai_provider.strip().lower()
    if provider_name == "mock":
        from app.providers.mock.provider import MockAIProvider
        return MockAIProvider()
    raise ConfigurationError(
        f"Unsupported AI provider '{resolved.ai_provider}'. Supported providers: mock"
    )
```

Key properties:

- **Configuration-driven selection.** The provider is chosen entirely by `Settings.ai_provider` (backed by the `AI_PROVIDER` environment variable, normalized to lowercase).
- **Localized imports.** The `MockAIProvider` import happens inside the `if` branch, so importing the factory does not pull in every provider's dependencies — this matters once Azure/AWS SDK-backed providers exist.
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

FastAPI resolves `get_ai_provider` as a dependency of `get_communication_analysis_service`, which is itself injected into the `POST /api/v1/communications/analyze` route. This is the only place `fastapi.Depends` is combined with provider resolution — the factory function itself has no FastAPI dependency.

## Explicit Failure for Unsupported Providers

If `AI_PROVIDER` is set to anything other than `mock` (e.g. `azure`, `aws`, `openai`), `create_ai_provider` raises `ConfigurationError` immediately. There is no `try`/`except` around the lookup that would swallow the error, and no default case that returns `MockAIProvider()`.

## Why No Silent Fallback Is Allowed

A silent fallback to `MockAIProvider` when an unsupported provider is configured would mean:

- Production misconfiguration (e.g. a typo in `AI_PROVIDER`, or a not-yet-implemented provider name) would silently serve deterministic mock analysis instead of failing loudly.
- Operators would have no signal that the intended provider was never actually selected.

Failing explicitly with `ConfigurationError` — which is translated into an HTTP `500` by the exception handler in `app/main.py` — surfaces misconfiguration immediately instead of masking it.

## Azure and AWS: Future Adapters Only

`app/providers/azure/__init__.py` and `app/providers/aws/__init__.py` exist as empty scaffold packages. **No Azure AI Foundry or Amazon Bedrock code is implemented.** When added, each would be expected to:

- Implement `AIProvider` in its own module (mirroring `app/providers/mock/provider.py`).
- Be selected via a new branch in `create_ai_provider`, matching `AI_PROVIDER=azure` / `AI_PROVIDER=aws`.
- Keep all cloud SDK imports confined to its own package, per `.cursor/rules/contextmesh.mdc`.

See [`docs/cloud/`](../cloud/README.md) for the (currently placeholder) planning documents for these future adapters.
