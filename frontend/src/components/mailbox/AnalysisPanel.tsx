import { forwardRef } from "react";

import type { CommunicationAnalysisResponse } from "../../api/mailbox";
import { ActionItemsList } from "./ActionItemsList";
import { CategoryBadge } from "./CategoryBadge";
import { DraftReplyPanel } from "./DraftReplyPanel";
import { PriorityBadge } from "./PriorityBadge";
import { SummarySection } from "./SummarySection";

type AnalysisPanelProps = {
  result: CommunicationAnalysisResponse;
};

export const AnalysisPanel = forwardRef<HTMLElement, AnalysisPanelProps>(function AnalysisPanel(
  { result },
  ref,
) {
  const analysis = result.analysis;

  return (
    <article
      ref={ref}
      tabIndex={-1}
      className="space-y-5 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-slate-900"
      aria-labelledby="ai-analysis-heading"
    >
      <h3 id="ai-analysis-heading" className="text-base font-semibold text-slate-900">
        AI Analysis
      </h3>
      <SummarySection text={analysis.summary?.text} />
      <section aria-labelledby="analysis-priority-heading">
        <h4 id="analysis-priority-heading" className="text-sm font-semibold text-slate-900">
          Priority
        </h4>
        <div className="mt-2">
          <PriorityBadge level={analysis.priority?.level} rationale={analysis.priority?.rationale} />
        </div>
      </section>
      <section aria-labelledby="analysis-category-heading">
        <h4 id="analysis-category-heading" className="text-sm font-semibold text-slate-900">
          Category
        </h4>
        <div className="mt-2">
          <CategoryBadge category={analysis.category} />
        </div>
      </section>
      <ActionItemsList items={analysis.action_items} />
      <DraftReplyPanel body={analysis.draft_reply?.body} />
    </article>
  );
});
