import { formatMailboxTimestamp } from "../../lib/formatTimestamp";
import type { AttachmentAnalysisResponse } from "../../api/attachments";
import { ActionItemsList } from "./ActionItemsList";
import { CategoryBadge } from "./CategoryBadge";
import { PriorityBadge } from "./PriorityBadge";
import { SummarySection } from "./SummarySection";
import { ATTACHMENT_RESULT_BOUNDARY, ATTACHMENT_RESULT_HEADING, TRUNCATION_INDICATOR } from "./attachmentCopy";

type AttachmentAnalysisPanelProps = {
  result: AttachmentAnalysisResponse;
  headingId?: string;
};

export function AttachmentAnalysisPanel({
  result,
  headingId = "attachment-analysis-heading",
}: AttachmentAnalysisPanelProps) {
  const analyzedAt = formatMailboxTimestamp(result.created_at);

  return (
    <article
      className="min-w-0 space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4"
      aria-labelledby={headingId}
    >
      <div className="min-w-0">
        <h5 id={headingId} className="text-sm font-semibold text-slate-900">
          {ATTACHMENT_RESULT_HEADING}
        </h5>
        <p className="mt-1 text-sm text-slate-600">{ATTACHMENT_RESULT_BOUNDARY}</p>
      </div>
      <SummarySection text={result.summary?.text} headingId={`${headingId}-summary`} />
      <section aria-labelledby={`${headingId}-priority`}>
        <h6 id={`${headingId}-priority`} className="text-sm font-semibold text-slate-900">
          Priority
        </h6>
        <div className="mt-2">
          <PriorityBadge level={result.priority?.level} rationale={result.priority?.rationale} />
        </div>
      </section>
      <section aria-labelledby={`${headingId}-category`}>
        <h6 id={`${headingId}-category`} className="text-sm font-semibold text-slate-900">
          Category
        </h6>
        <div className="mt-2">
          <CategoryBadge category={result.category} />
        </div>
      </section>
      <ActionItemsList items={result.action_items} headingId={`${headingId}-action-items`} />
      {result.truncated ? (
        <p className="text-sm text-slate-600" data-testid="attachment-truncation-indicator">
          {TRUNCATION_INDICATOR}
        </p>
      ) : null}
      {result.warnings.length > 0 ? (
        <section aria-labelledby={`${headingId}-warnings`}>
          <h6 id={`${headingId}-warnings`} className="text-sm font-semibold text-slate-900">
            Warnings
          </h6>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {result.warnings.map((warning, index) => (
              <li key={`${warning}-${index}`} className="min-w-0 break-words">
                {warning}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <dl className="grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
        {result.provider ? (
          <div>
            <dt className="text-slate-500">Provider</dt>
            <dd>{result.provider}</dd>
          </div>
        ) : null}
        {analyzedAt ? (
          <div>
            <dt className="text-slate-500">Analyzed</dt>
            <dd>{analyzedAt}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}
