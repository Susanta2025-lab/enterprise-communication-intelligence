import type { TabularAnalysisResult } from "../../api/attachments";

type TabularAnalysisPanelProps = {
  result: TabularAnalysisResult;
  headingId: string;
  attachmentTruncated: boolean;
  attachmentWarnings: readonly string[];
};

export function TabularAnalysisPanel({
  result,
  headingId,
  attachmentTruncated,
  attachmentWarnings,
}: TabularAnalysisPanelProps) {
  const sections = [
    ["important-fields", "Important fields", result.important_fields],
    ["patterns", "Notable values / patterns", result.notable_values_or_patterns],
    ["data-quality", "Data-quality observations", result.data_quality_observations],
    ["potential-dates", "Potential dates", result.potential_dates],
    ["potential-amounts", "Potential amounts", result.potential_amounts],
    ["potential-actions", "Potential action mentions", result.potential_action_mentions],
    ["warnings", "Warnings", [...new Set([...attachmentWarnings, ...result.warnings])]],
    ["limitations", "Limitations", result.limitations],
  ] as const;

  return (
    <div className="min-w-0 space-y-4 break-words">
      <p className="text-sm text-slate-600">
        AI observations are advisory. Potential dates, amounts, and action mentions require your review.
      </p>
      {result.source_truncated || attachmentTruncated ? (
        <p role="status" className="rounded-md border border-slate-300 bg-white p-3 text-sm text-slate-800">
          Analysis used a bounded sample of this workbook.
        </p>
      ) : null}
      <section aria-labelledby={`${headingId}-summary`}>
        <h6 id={`${headingId}-summary`} className="text-sm font-semibold text-slate-900">Workbook summary</h6>
        <p className="mt-2 text-sm text-slate-800">{result.summary}</p>
      </section>
      {result.sheet_summaries.length > 0 ? (
        <section aria-labelledby={`${headingId}-sheets`}>
          <h6 id={`${headingId}-sheets`} className="text-sm font-semibold text-slate-900">Sheet summaries</h6>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-700">
            {result.sheet_summaries.map((sheet, index) => (
              <li key={index}>
                <p className="font-medium">{sheet.sheet_name || "Unnamed sheet"}</p>
                <p>{sheet.summary}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {sections.map(([key, title, items]) => items.length > 0 ? (
        <section key={key} aria-labelledby={`${headingId}-${key}`}>
          <h6 id={`${headingId}-${key}`} className="text-sm font-semibold text-slate-900">{title}</h6>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {items.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </section>
      ) : null)}
    </div>
  );
}
