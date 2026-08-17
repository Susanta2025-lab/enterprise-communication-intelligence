"""Microsoft Foundry implementation of the AIProvider contract."""

import time
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.providers.common.output import (
    AnalysisOutputError,
    parse_analysis_output,
    to_communication_analysis,
)
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from app.providers.microsoft_foundry.output import FOUNDRY_ANALYSIS_JSON_SCHEMA

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

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication through Microsoft Foundry and map domain results."""
        message_id = request.message.message_id
        logger.info(
            "microsoft_foundry_analysis_requested",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            message_id=message_id,
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
                message_id=message_id,
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "microsoft_foundry_analysis_completed",
            provider=self.PROVIDER_NAME,
            deployment=self._model_deployment,
            message_id=message_id,
            duration_ms=elapsed_ms(started_at),
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
