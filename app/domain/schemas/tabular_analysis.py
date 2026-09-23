"""Provider-neutral schemas for advisory XLSX / tabular AI analysis (Phase 21C).

Results are advisory observations only. They must not create workflow actions,
deadlines, obligations, BusinessContext links, or persistence rows.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.attachment_policy import XLSX_AI_INPUT_MAX_CHARS
from app.domain.models.tabular_analysis import (
    TabularAnalysisResult as TabularAnalysisResult,
)
from app.domain.models.tabular_analysis import (
    TabularSheetSummary as TabularSheetSummary,
)


class TabularAnalysisRequest(BaseModel):
    """Bounded, fenced-ready workbook sample for provider-neutral tabular AI.

    ``workbook_text`` is untrusted data only. It must never be concatenated into
    system instructions. Input must already respect ``XLSX_AI_INPUT_MAX_CHARS``.
    """

    model_config = ConfigDict(extra="forbid")

    workbook_text: str = Field(min_length=1, max_length=XLSX_AI_INPUT_MAX_CHARS)
    source_truncated: bool = False
    parser_truncated: bool = False
    parser_warnings: tuple[str, ...] = ()
    sheet_count: int | None = Field(default=None, ge=0)
    cells_emitted: int | None = Field(default=None, ge=0)
    input_character_count: int = Field(ge=1, le=XLSX_AI_INPUT_MAX_CHARS)
