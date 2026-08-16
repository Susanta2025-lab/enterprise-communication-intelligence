"""Configuration-driven AI provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces import AIProvider

_SUPPORTED_PROVIDERS = ("mock", "microsoft_foundry", "amazon_bedrock")


def create_ai_provider(settings: Settings | None = None) -> AIProvider:
    """Create an AI provider based on application settings.

    Supported providers:
    - ``mock``: deterministic offline provider for local development and tests
    - ``microsoft_foundry``: Microsoft Foundry Responses API provider
    - ``amazon_bedrock``: Amazon Bedrock Converse API provider

    Unsupported provider names raise ``ConfigurationError``. There is no silent
    fallback to another provider.
    """
    resolved = settings or get_settings()
    provider_name = resolved.ai_provider.strip().lower()

    if provider_name == "mock":
        from app.providers.mock.provider import MockAIProvider

        return MockAIProvider()

    if provider_name == "microsoft_foundry":
        from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider

        endpoint = resolved.foundry_project_endpoint
        deployment = resolved.foundry_model_deployment
        if not endpoint or not deployment:
            raise ConfigurationError(
                "Microsoft Foundry provider requires FOUNDRY_PROJECT_ENDPOINT "
                "and FOUNDRY_MODEL_DEPLOYMENT."
            )
        return MicrosoftFoundryProvider(
            project_endpoint=endpoint,
            model_deployment=deployment,
        )

    if provider_name == "amazon_bedrock":
        from app.providers.amazon_bedrock.provider import AmazonBedrockProvider

        region = resolved.bedrock_region
        model_id = resolved.bedrock_model_id
        if not region or not model_id:
            raise ConfigurationError(
                "Amazon Bedrock provider requires BEDROCK_REGION and BEDROCK_MODEL_ID."
            )
        return AmazonBedrockProvider(
            region=region,
            model_id=model_id,
        )

    supported = ", ".join(_SUPPORTED_PROVIDERS)
    raise ConfigurationError(
        f"Unsupported AI provider '{resolved.ai_provider}'. Supported providers: {supported}"
    )
