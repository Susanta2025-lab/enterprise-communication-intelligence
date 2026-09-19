"""Shared LLM adapter analysis and suggestion mechanics."""

from app.providers.common.output import (
    AnalysisActionItemOutput,
    AnalysisDraftReplyOutput,
    AnalysisOutput,
    AnalysisOutputError,
    parse_analysis_output,
    to_communication_analysis,
)
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from app.providers.common.suggestion_output import (
    ContextSuggestionItemOutput,
    ContextSuggestionOutput,
    ContextSuggestionOutputError,
    parse_context_suggestion_output,
    to_business_context_suggestion_result,
)
from app.providers.common.suggestion_prompts import (
    CONTEXT_SUGGESTION_SYSTEM_PROMPT,
    build_context_suggestion_user_prompt,
)

__all__ = [
    "AnalysisActionItemOutput",
    "AnalysisDraftReplyOutput",
    "AnalysisOutput",
    "AnalysisOutputError",
    "CONTEXT_SUGGESTION_SYSTEM_PROMPT",
    "ContextSuggestionItemOutput",
    "ContextSuggestionOutput",
    "ContextSuggestionOutputError",
    "SYSTEM_PROMPT",
    "build_context_suggestion_user_prompt",
    "build_user_prompt",
    "parse_analysis_output",
    "parse_context_suggestion_output",
    "to_business_context_suggestion_result",
    "to_communication_analysis",
]
