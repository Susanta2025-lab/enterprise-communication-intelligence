import type { AnalysisActionItem } from "../../api/mailbox";
import { formatMailboxTimestamp } from "../../lib/formatTimestamp";
import { NO_ACTION_ITEMS_COPY, priorityLabel } from "./copy";

type ActionItemsListProps = {
  items: readonly AnalysisActionItem[] | null | undefined;
};

export function ActionItemsList({ items }: ActionItemsListProps) {
  const actionItems = items ?? [];

  return (
    <section aria-labelledby="analysis-action-items-heading" className="min-w-0">
      <h5 id="analysis-action-items-heading" className="text-sm font-semibold text-slate-900">
        Action items
      </h5>
      {actionItems.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">{NO_ACTION_ITEMS_COPY}</p>
      ) : (
        <ul
          aria-label="Action items"
          className="mt-2 list-disc space-y-3 pl-5 text-sm text-slate-800"
        >
          {actionItems.map((item, index) => (
            <li key={`${item.description}-${index}`} className="min-w-0">
              <p className="min-w-0 break-words">{item.description}</p>
              {item.owner ? (
                <p className="min-w-0 break-words text-slate-600">Owner: {item.owner}</p>
              ) : null}
              {formatMailboxTimestamp(item.due_at) ? (
                <p className="text-slate-600">Due: {formatMailboxTimestamp(item.due_at)}</p>
              ) : null}
              {item.priority ? (
                <p className="text-slate-600">Priority: {priorityLabel(item.priority)}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
