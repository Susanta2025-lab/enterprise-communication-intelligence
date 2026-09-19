"""Microsoft Foundry implementation of the AIProvider contract."""

import time
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.exceptions import AttachmentImageInputUnsupportedError
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
)
from app.providers.common.output import (
    AnalysisOutputError,
    parse_analysis_output,
    to_communication_analysis,
)
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from app.providers.common.suggestion_output import (
    parse_context_suggestion_output,
    to_business_context_suggestion_result,
)
from app.providers.common.suggestion_prompts import (
    CONTEXT_SUGGESTION_SYSTEM_PROMPT,
    build_context_suggestion_user_prompt,
)
from app.providers.microsoft_foundry.output import (
    FOUNDRY_ANALYSIS_JSON_SCHEMA,
    FOUNDRY_CONTEXT_SUGGESTION_JSON_SCHEMA,
)

logger = get_logger(__name__)


class MicrosoftFoundryProvider(AIProvider):
    """Analyze communications through Microsoft Foundry Responses API."""

    PROVIDER_NAME = "microsoft_foundry"

    def __init__(
        self,
        *,
        project_endpoint: str,
        model_deployment: str,
        openai_client: Any | None = None,
    ) -> None:
        """Store Foundry connection settings and an optional injected client.

        The OpenAI-compatible client is created lazily on first use so the
        factory can construct this provider without contacting Azure. Tests may
        inject ``openai_client`` to stay fully offline.
        """
        endpoint = project_endpoint.strip()
        deployment = model_deployment.strip()
        if not endpoint or not deployment:
            raise ConfigurationError(
                "Microsoft Foundry provider requires FOUNDRY_PROJECT_ENDPOINT "
                "and FOUNDRY_MODEL_DEPLOYMENT."
            )

        self._project_endpoint = endpoint
        self._model_deployment = deployment
        self._openai_client = openai_client
        self._credential: Any | None = None
        self._project_client: Any | None = None

    def supports_image_input(self) -> bool:
        """Foundry image input is not declared for the current text adapter."""
        return False

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication through Microsoft Foundry and map domain results."""
        if request.attachment_images:
            raise AttachmentImageInputUnsupportedError()
        logger.info(
            "microsoft_foundry_analysis_requested",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            operation="analyze",
        )
        started_at = time.perf_counter()

        try:
            response = self._get_openai_client().responses.create(
                model=self._model_deployment,
                instructions=SYSTEM_PROMPT,
                input=build_user_prompt(request),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "communication_analysis",
                        "strict": True,
                        "schema": FOUNDRY_ANALYSIS_JSON_SCHEMA,
                    }
                },
            )
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str):
                raise AnalysisOutputError(
                    "Microsoft Foundry returned a response without JSON text output."
                )

            output = parse_analysis_output(output_text)
            analysis = to_communication_analysis(output, request)
            result = CommunicationAnalysisResult(
                analysis=analysis,
                provider=self.PROVIDER_NAME,
            )
        except Exception as exc:
            logger.error(
                "microsoft_foundry_analysis_failed",
                provider=self.PROVIDER_NAME,
                deployment=self._model_deployment,
                operation="analyze",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "microsoft_foundry_analysis_completed",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            operation="analyze",
            duration_ms=elapsed_ms(started_at),
        )
        return result

    def suggest_business_context(
        self,
        request: BusinessContextSuggestionRequest,
    ) -> BusinessContextSuggestionResult:
        """Suggest BusinessContext candidates through Microsoft Foundry."""
        logger.info(
            "microsoft_foundry_context_suggestion_requested",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            operation="suggest_business_context",
            candidate_count=len(request.candidates),
        )
        started_at = time.perf_counter()

        try:
            response = self._get_openai_client().responses.create(
                model=self._model_deployment,
                instructions=CONTEXT_SUGGESTION_SYSTEM_PROMPT,
                input=build_context_suggestion_user_prompt(request),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "business_context_suggestion",
                        "strict": True,
                        "schema": FOUNDRY_CONTEXT_SUGGESTION_JSON_SCHEMA,
                    }
                },
            )
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str):
                raise AnalysisOutputError(
                    "Microsoft Foundry returned a response without JSON text output."
                )

            output = parse_context_suggestion_output(output_text)
            result = to_business_context_suggestion_result(
                output,
                request,
                provider=self.PROVIDER_NAME,
            )
        except Exception as exc:
            logger.error(
                "microsoft_foundry_context_suggestion_failed",
                provider=self.PROVIDER_NAME,
                deployment=self._model_deployment,
                operation="suggest_business_context",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "microsoft_foundry_context_suggestion_completed",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            operation="suggest_business_context",
            duration_ms=elapsed_ms(started_at),
            suggestion_count=len(result.suggestions),
        )
        return result

    def _get_openai_client(self) -> Any:
        """Return a reusable OpenAI-compatible client from the Foundry project."""
        if self._openai_client is not None:
            return self._openai_client

        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(
            endpoint=self._project_endpoint,
            credential=self._credential,
        )
        self._openai_client = self._project_client.get_openai_client()
        return self._openai_client
