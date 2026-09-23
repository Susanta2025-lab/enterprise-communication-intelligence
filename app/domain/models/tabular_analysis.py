"""Bounded provider-neutral tabular output shared by analysis and persistence."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Text200 = Annotated[str, Field(max_length=200)]
Text300 = Annotated[str, Field(max_length=300)]


class TabularSheetSummary(BaseModel):
    """Concise advisory summary for one supplied sheet."""

    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    sheet_name: str = Field(default="", max_length=200)
    summary: str = Field(min_length=1, max_length=500)


class TabularAnalysisResult(BaseModel):
    """Validated advisory tabular intelligence. Not durable domain entities.

    ``potential_dates`` / ``potential_amounts`` / ``potential_action_mentions``
    are textual observations only — not Phase 22 Deadline / Obligation /
    workflow ActionItem objects.
    """

    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    summary: str = Field(min_length=1, max_length=2_000)
    sheet_summaries: list[TabularSheetSummary] = Field(default_factory=list, max_length=10)
    important_fields: list[Text200] = Field(default_factory=list, max_length=20)
    notable_values_or_patterns: list[Text300] = Field(default_factory=list, max_length=20)
    data_quality_observations: list[Text300] = Field(default_factory=list, max_length=15)
    potential_dates: list[Text200] = Field(default_factory=list, max_length=15)
    potential_amounts: list[Text200] = Field(default_factory=list, max_length=15)
    potential_action_mentions: list[Text300] = Field(default_factory=list, max_length=15)
    warnings: list[Text200] = Field(default_factory=list, max_length=20)
    limitations: list[Text300] = Field(default_factory=list, max_length=10)
    source_truncated: bool = False
    provider: str | None = Field(
        default=None,
        max_length=64,
        description="Opaque provider identifier that produced the analysis.",
    )
