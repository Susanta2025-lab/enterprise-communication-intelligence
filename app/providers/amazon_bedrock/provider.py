"""Amazon Bedrock implementation of the AIProvider contract."""

from typing import Any

import boto3

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.providers.amazon_bedrock.output import (
    BEDROCK_ANALYSIS_JSON_SCHEMA,
    extract_converse_output_text,
)
from app.providers.common.output import parse_analysis_output, to_communication_analysis
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class AmazonBedrockProvider(AIProvider):
    """Analyze communications through Amazon Bedrock Converse API."""

    PROVIDER_NAME = "amazon_bedrock"

    def __init__(
        self,
        *,
        region: str,
        model_id: str,
        bedrock_runtime_client: Any | None = None,
    ) -> None:
        """Store Bedrock connection settings and an optional injected client.

        The Bedrock Runtime client is created lazily on first use so the factory
        can construct this provider without contacting AWS. Tests may inject
        ``bedrock_runtime_client`` to stay fully offline.
        """
        resolved_region = region.strip()
        resolved_model_id = model_id.strip()
        if not resolved_region or not resolved_model_id:
            raise ConfigurationError(
                "Amazon Bedrock provider requires BEDROCK_REGION and BEDROCK_MODEL_ID."
            )

        self._region = resolved_region
        self._model_id = resolved_model_id
        self._bedrock_runtime_client = bedrock_runtime_client

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication through Amazon Bedrock and map domain results."""
        logger.info(
            "amazon_bedrock_analysis_requested",
            model_id=self._model_id,
            region=self._region,
            message_id=request.message.message_id,
        )

        response = self._get_bedrock_runtime_client().converse(
            modelId=self._model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": build_user_prompt(request)}],
                }
            ],
            outputConfig={
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": BEDROCK_ANALYSIS_JSON_SCHEMA,
                            "name": "communication_analysis",
                            "description": "Structured communication analysis.",
                        }
                    },
                }
            },
        )
        output_text = extract_converse_output_text(response)
        output = parse_analysis_output(output_text)
        analysis = to_communication_analysis(output, request)
        return CommunicationAnalysisResult(
            analysis=analysis,
            provider=self.PROVIDER_NAME,
        )

    def _get_bedrock_runtime_client(self) -> Any:
        """Return a reusable Bedrock Runtime client for the configured region."""
        if self._bedrock_runtime_client is not None:
            return self._bedrock_runtime_client

        self._bedrock_runtime_client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
        )
        return self._bedrock_runtime_client
