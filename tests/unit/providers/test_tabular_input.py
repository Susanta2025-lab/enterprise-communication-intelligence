"""Unit tests for Phase 21C tabular AI input bounding."""

from __future__ import annotations

from app.domain.attachment_policy import XLSX_AI_INPUT_MAX_CHARS
from app.domain.models.workbook_extraction import (
    SheetExtraction,
    WorkbookExtraction,
    XlsxSheetVisibility,
)
from app.providers.common.tabular_input import (
    prepare_tabular_analysis_request,
    prepare_tabular_analysis_request_from_text,
)


def _sheet(
    name: str,
    *,
    rows: tuple[tuple[str, ...], ...],
    index: int = 0,
    header: tuple[str, ...] = (),
) -> SheetExtraction:
    cells = sum(len(row) for row in rows) + len(header)
    return SheetExtraction(
        name=name,
        visibility=XlsxSheetVisibility.VISIBLE,
        index=index,
        header_inferred=bool(header),
        header_cells=header,
        data_rows=rows,
        rows_processed=len(rows),
        columns_processed=max((len(row) for row in rows), default=len(header)),
        cells_emitted=cells,
    )


def _workbook(*sheets: SheetExtraction, truncated: bool = False) -> WorkbookExtraction:
    return WorkbookExtraction(
        sheet_count=len(sheets),
        sheets_processed=len(sheets),
        sheets=sheets,
        truncated=truncated,
        cells_emitted=sum(sheet.cells_emitted for sheet in sheets),
        characters_emitted=0,
    )


def test_ordinary_workbook_sample_under_cap() -> None:
    extraction = _workbook(
        _sheet(
            "Orders",
            header=("Item", "Amount"),
            rows=(("Widget", "10"), ("Gadget", "20")),
        )
    )
    request = prepare_tabular_analysis_request(extraction)
    assert request.input_character_count <= XLSX_AI_INPUT_MAX_CHARS
    assert request.source_truncated is False
    assert "SHEET 1" in request.workbook_text
    assert "Widget" in request.workbook_text
    assert "xlsx_ai_input_truncated" not in request.parser_warnings


def test_multi_sheet_and_hidden_metadata_retained() -> None:
    hidden = _sheet("Secret", rows=(("x",),), index=1)
    hidden = hidden.model_copy(update={"visibility": XlsxSheetVisibility.HIDDEN})
    extraction = _workbook(
        _sheet("Visible", rows=(("a",),), index=0),
        hidden,
    )
    request = prepare_tabular_analysis_request(extraction)
    assert "visibility: hidden" in request.workbook_text
    assert "name: Secret" in request.workbook_text
    assert request.sheet_count == 2


def test_parser_truncation_propagated() -> None:
    extraction = _workbook(
        _sheet("S", rows=(("v",),)),
        truncated=True,
    )
    request = prepare_tabular_analysis_request(extraction)
    assert request.parser_truncated is True
    assert request.source_truncated is True


def test_ai_payload_cap_enforced_deterministically() -> None:
    # Many long rows force structured truncation under a small test cap.
    rows = tuple((f"cell-{i:04d}-{'x' * 40}",) for i in range(80))
    extraction = _workbook(_sheet("Wide", rows=rows, header=("Col",)))
    request = prepare_tabular_analysis_request(extraction, max_chars=1_200)
    assert request.input_character_count <= 1_200
    assert request.source_truncated is True
    assert "xlsx_ai_input_truncated" in request.parser_warnings
    assert "[AI_INPUT_TRUNCATED]" in request.workbook_text
    # Deterministic: identical input → identical bounded payload.
    again = prepare_tabular_analysis_request(extraction, max_chars=1_200)
    assert again.workbook_text == request.workbook_text


def test_utf8_multibyte_near_limit_does_not_split_codepoints() -> None:
    # Each emoji is one Python str code point; slicing must remain valid text.
    payload = "WORKBOOK\n" + ("🙂" * 100) + "\nROW\n"
    request = prepare_tabular_analysis_request_from_text(payload, max_chars=40)
    assert request.input_character_count <= 40
    assert request.workbook_text.encode("utf-8")
    assert "\ud800" not in request.workbook_text


def test_from_text_respects_hard_cap() -> None:
    text = "A" * (XLSX_AI_INPUT_MAX_CHARS + 500)
    request = prepare_tabular_analysis_request_from_text(text)
    assert request.input_character_count <= XLSX_AI_INPUT_MAX_CHARS
    assert request.source_truncated is True
    assert len(request.workbook_text) <= XLSX_AI_INPUT_MAX_CHARS
