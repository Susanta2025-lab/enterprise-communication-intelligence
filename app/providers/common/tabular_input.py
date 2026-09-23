"""Deterministic AI-input preparation for Phase 21C tabular analysis.

Enforces the provider-neutral ``XLSX_AI_INPUT_MAX_CHARS`` cap before any
provider invocation. Truncation prefers sheet/row boundaries and never
splits UTF-8 code points (Python ``str`` slicing).
"""

from __future__ import annotations

from app.domain.attachment_policy import XLSX_AI_INPUT_MAX_CHARS
from app.domain.models.workbook_extraction import SheetExtraction, WorkbookExtraction
from app.domain.schemas.tabular_analysis import TabularAnalysisRequest

_AI_INPUT_TRUNCATED_WARNING = "xlsx_ai_input_truncated"
_TRUNCATION_MARKER = "[AI_INPUT_TRUNCATED]"
_ROW_JOIN = " | "


def prepare_tabular_analysis_request(
    extraction: WorkbookExtraction,
    *,
    max_chars: int = XLSX_AI_INPUT_MAX_CHARS,
) -> TabularAnalysisRequest:
    """Build a bounded tabular AI request from Phase 21B extraction output."""
    if max_chars < 1 or max_chars > XLSX_AI_INPUT_MAX_CHARS:
        raise ValueError("max_chars must be within the locked AI input bound")

    text, ai_truncated = _serialize_bounded(extraction, max_chars=max_chars)
    if not text.strip():
        raise ValueError("workbook extraction produced empty AI input")

    warnings = list(extraction.warnings)
    if ai_truncated:
        warnings = _append_unique(warnings, _AI_INPUT_TRUNCATED_WARNING)

    source_truncated = bool(extraction.truncated or ai_truncated)
    return TabularAnalysisRequest(
        workbook_text=text,
        source_truncated=source_truncated,
        parser_truncated=extraction.truncated,
        parser_warnings=tuple(warnings),
        sheet_count=extraction.sheet_count,
        cells_emitted=extraction.cells_emitted,
        input_character_count=len(text),
    )


def prepare_tabular_analysis_request_from_text(
    workbook_text: str,
    *,
    parser_truncated: bool = False,
    parser_warnings: tuple[str, ...] = (),
    sheet_count: int | None = None,
    cells_emitted: int | None = None,
    max_chars: int = XLSX_AI_INPUT_MAX_CHARS,
) -> TabularAnalysisRequest:
    """Bound a pre-serialized workbook sample for tabular AI (tests / callers)."""
    if max_chars < 1 or max_chars > XLSX_AI_INPUT_MAX_CHARS:
        raise ValueError("max_chars must be within the locked AI input bound")

    normalized = workbook_text if workbook_text.endswith("\n") else f"{workbook_text}\n"
    ai_truncated = False
    if len(normalized) > max_chars:
        normalized = _truncate_at_line_boundary(normalized, max_chars)
        ai_truncated = True

    if not normalized.strip():
        raise ValueError("workbook text produced empty AI input")

    warnings = list(parser_warnings)
    if ai_truncated:
        warnings = _append_unique(warnings, _AI_INPUT_TRUNCATED_WARNING)

    return TabularAnalysisRequest(
        workbook_text=normalized,
        source_truncated=bool(parser_truncated or ai_truncated),
        parser_truncated=parser_truncated,
        parser_warnings=tuple(warnings),
        sheet_count=sheet_count,
        cells_emitted=cells_emitted,
        input_character_count=len(normalized),
    )


def _serialize_bounded(
    extraction: WorkbookExtraction,
    *,
    max_chars: int,
) -> tuple[str, bool]:
    """Serialize with hard AI cap; truncate at sheet/row boundaries when needed."""
    header = [
        "WORKBOOK",
        f"kind: {extraction.kind}",
        f"sheet_count: {extraction.sheet_count}",
        f"sheets_processed: {extraction.sheets_processed}",
        f"sheets_skipped: {extraction.sheets_skipped}",
        f"truncated: {'true' if extraction.truncated else 'false'}",
        f"cells_emitted: {extraction.cells_emitted}",
        f"warnings: {_format_list(extraction.warnings)}",
        f"truncation_reasons: {_format_list(extraction.truncation_reasons)}",
        "",
    ]
    lines = list(header)
    ai_truncated = False
    sheet_number = 0

    for sheet in extraction.sheets:
        if sheet.skipped:
            block = [
                f"SHEET SKIPPED index={sheet.index}",
                f"name: {sheet.name}",
                f"visibility: {sheet.visibility.value}",
                f"skip_reason: {sheet.skip_reason or ''}",
                "",
            ]
            candidate = _join_lines([*lines, *block])
            if len(candidate) > max_chars:
                ai_truncated = True
                break
            lines.extend(block)
            continue

        sheet_number += 1
        sheet_header = _sheet_header_lines(sheet, sheet_number)
        candidate = _join_lines([*lines, *sheet_header])
        if len(candidate) > max_chars:
            ai_truncated = True
            break
        lines.extend(sheet_header)

        for row in sheet.data_rows:
            row_line = _join_row(row)
            candidate = _join_lines([*lines, row_line, ""])
            # Keep room to close the sheet with a blank line; check row alone first.
            row_candidate = _join_lines([*lines, row_line])
            if len(row_candidate) > max_chars:
                ai_truncated = True
                break
            lines.append(row_line)
        else:
            lines.append("")
            continue
        break

    text = _join_lines(lines)
    if ai_truncated:
        text = _append_truncation_marker(text, max_chars)
    elif len(text) > max_chars:
        # Pathological header-only overflow (should be rare).
        text = _truncate_at_line_boundary(text, max_chars)
        ai_truncated = True
    return text, ai_truncated


def _sheet_header_lines(sheet: SheetExtraction, sheet_number: int) -> list[str]:
    lines = [
        f"SHEET {sheet_number}",
        f"name: {sheet.name}",
        f"visibility: {sheet.visibility.value}",
    ]
    if sheet.source_max_row is not None or sheet.source_max_column is not None:
        row_part = str(sheet.source_max_row) if sheet.source_max_row is not None else ""
        col_part = (
            str(sheet.source_max_column) if sheet.source_max_column is not None else ""
        )
        lines.append(f"dimensions: rows={row_part} cols={col_part}")
    lines.append(f"header_inferred: {'true' if sheet.header_inferred else 'false'}")
    if sheet.header_inferred:
        lines.append(f"header: {_join_row(sheet.header_cells)}")
    lines.append(f"sampled_data_rows: {len(sheet.data_rows)}")
    lines.append(f"columns: {sheet.columns_processed}")
    lines.append(f"truncated: {'true' if sheet.truncated else 'false'}")
    if sheet.truncation_reasons:
        lines.append(f"truncation_reasons: {_format_list(sheet.truncation_reasons)}")
    lines.append("---")
    return lines


def _append_truncation_marker(text: str, max_chars: int) -> str:
    marker_block = f"\n{_TRUNCATION_MARKER}\n"
    if len(text) + len(marker_block) <= max_chars:
        return text.rstrip("\n") + marker_block
    return _truncate_at_line_boundary(text, max_chars)


def _truncate_at_line_boundary(text: str, max_chars: int) -> str:
    """Truncate to ``max_chars`` without splitting a Unicode code point."""
    if max_chars < 1:
        return ""
    marker = f"{_TRUNCATION_MARKER}\n"
    if max_chars <= len(marker):
        return marker[:max_chars]

    budget = max_chars - len(marker)
    chunk = text[:budget]
    newline = chunk.rfind("\n")
    if newline > 0:
        chunk = chunk[: newline + 1]
    else:
        chunk = f"{chunk.rstrip()}\n" if chunk.strip() else ""
        if len(chunk) > budget:
            chunk = text[: max(0, budget - 1)].rstrip() + "\n"

    result = chunk.rstrip("\n") + "\n" + marker
    if len(result) > max_chars:
        result = result[:max_chars]
    return result


def _join_lines(lines: list[str]) -> str:
    return "\n".join(lines) + ("\n" if lines else "")


def _join_row(cells: tuple[str, ...]) -> str:
    return _ROW_JOIN.join(cells)


def _format_list(values: tuple[str, ...] | list[str]) -> str:
    if not values:
        return "(none)"
    return ", ".join(values)


def _append_unique(values: list[str], item: str) -> list[str]:
    if item in values:
        return values
    return [*values, item]
