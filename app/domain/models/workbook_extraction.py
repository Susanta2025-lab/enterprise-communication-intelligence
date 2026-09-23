"""Provider-neutral bounded XLSX workbook extraction models (Phase 21B).

These types describe deterministic parser output only. They are not AI
interpretation, not persistence schemas, and never retain raw workbook bytes.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.validation import require_non_empty_text


class XlsxSheetVisibility(StrEnum):
    """Workbook sheet visibility as declared by the file (never unhidden)."""

    VISIBLE = "visible"
    HIDDEN = "hidden"
    VERY_HIDDEN = "very_hidden"


class XlsxCellValueType(StrEnum):
    """Normalized cell value kind. Formulas are data, never executed."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    BLANK = "blank"
    ERROR = "error"
    FORMULA = "formula"


class XlsxTruncationReason(StrEnum):
    """Stable machine-readable truncation / sampling reasons."""

    SHEETS = "xlsx_truncated_sheets"
    ROWS = "xlsx_truncated_rows"
    COLUMNS = "xlsx_truncated_columns"
    CELLS = "xlsx_truncated_cells"
    CHARACTERS = "xlsx_truncated_characters"
    CELL_CHARS = "xlsx_truncated_cell_chars"
    SKIPPED_SHEET = "xlsx_sheet_skipped"


class ExtractedCell(BaseModel):
    """One emitted cell after safe normalization. Untrusted data only."""

    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=1)
    column: int = Field(ge=1)
    text: str
    value_type: XlsxCellValueType
    is_formula: bool = False


class SheetExtraction(BaseModel):
    """Bounded extraction for one worksheet."""

    model_config = ConfigDict(extra="forbid")

    name: str
    visibility: XlsxSheetVisibility
    index: int = Field(ge=0)
    header_inferred: bool = False
    header_cells: tuple[str, ...] = ()
    data_rows: tuple[tuple[str, ...], ...] = ()
    rows_processed: int = Field(default=0, ge=0)
    columns_processed: int = Field(default=0, ge=0)
    cells_emitted: int = Field(default=0, ge=0)
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()
    skipped: bool = False
    skip_reason: str | None = None
    source_max_row: int | None = Field(default=None, ge=0)
    source_max_column: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Sheet names are untrusted display data; blank is allowed."""
        return value.strip() if value else ""


class WorkbookExtraction(BaseModel):
    """Bounded workbook sample suitable for later Phase 21C AI fencing."""

    model_config = ConfigDict(extra="forbid")

    kind: str = "xlsx"
    version: int = 1
    sheet_count: int = Field(ge=0)
    sheets_processed: int = Field(ge=0)
    sheets_skipped: int = Field(default=0, ge=0)
    sheets: tuple[SheetExtraction, ...] = ()
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()
    cells_emitted: int = Field(default=0, ge=0)
    characters_emitted: int = Field(default=0, ge=0)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        """Only the XLSX extraction kind is supported in Phase 21B."""
        normalized = require_non_empty_text(value, "kind")
        if normalized != "xlsx":
            raise ValueError("kind must be xlsx")
        return normalized
