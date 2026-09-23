import type { TabularAnalysisResult } from "../api/attachments";

export function tabularResult(overrides: Partial<TabularAnalysisResult> = {}): TabularAnalysisResult {
  return {
    summary: "The workbook contains a quarterly budget review.",
    sheet_summaries: [{ sheet_name: "Budget", summary: "Quarterly estimates by department." }],
    important_fields: ["Department"],
    notable_values_or_patterns: ["Several estimates repeat."],
    data_quality_observations: ["Some rows have blank descriptions."],
    potential_dates: ["2026-10-01 may be a review date."],
    potential_amounts: ["EUR 200 appears in an estimate."],
    potential_action_mentions: ["A note mentions reviewing estimates."],
    warnings: ["Formula text was included without evaluation."],
    limitations: ["Currency and date interpretation require review."],
    source_truncated: false,
    provider: "mock",
    ...overrides,
  };
}
