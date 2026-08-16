"""Shared LLM adapter analysis mechanics."""

from app.providers.common.output import (
    AnalysisActionItemOutput,
    AnalysisDraftReplyOutput,
    AnalysisOutput,
    AnalysisOutputError,
    parse_analysis_output,
    to_communication_analysis,
)
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt

__all__ = [
    "AnalysisActionItemOutput",
    "AnalysisDraftReplyOutput",
    "AnalysisOutput",
    "AnalysisOutputError",
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "parse_analysis_output",
    "to_communication_analysis",
]
