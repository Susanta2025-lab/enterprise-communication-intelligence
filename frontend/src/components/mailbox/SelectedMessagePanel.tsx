import type { ReactNode } from "react";

import type { MailboxMessageListItem } from "../../api/mailbox";
import { formatMailboxTimestamp } from "../../lib/formatTimestamp";
import { providerLabel } from "../connectors/copy";
import { displaySubject } from "./copy";

type SelectedMessagePanelProps = {
  item: MailboxMessageListItem | null;
  provider: string;
  onBackToList?: () => void;
  children?: ReactNode;
};

export function SelectedMessagePanel({
  item,
  provider,
  onBackToList,
  children,
}: SelectedMessagePanelProps) {
  if (!item) {
    return (
      <aside className="min-w-0 rounded-lg border border-slate-200 bg-white p-5" aria-label="Selected message">
        <p className="text-sm text-slate-600">Select a message to view its details.</p>
      </aside>
    );
  }

  const sent = formatMailboxTimestamp(item.sent_at);
  const received = formatMailboxTimestamp(item.received_at);

  return (
    <aside className="min-w-0 rounded-lg border border-slate-200 bg-white p-5" aria-label="Selected message">
      {onBackToList ? (
        <button
          type="button"
          className="mb-3 min-h-11 text-sm font-medium text-slate-700 underline lg:hidden"
          onClick={onBackToList}
        >
          Back to message list
        </button>
      ) : null}
      <h3 className="text-base font-semibold text-slate-900">Selected message</h3>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        {providerLabel(provider)}
      </p>
      <dl className="mt-4 space-y-3 text-sm">
        <div className="min-w-0">
          <dt className="text-slate-500">Sender</dt>
          <dd className="min-w-0 break-words font-medium text-slate-900">{item.sender}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-slate-500">Subject</dt>
          <dd
            className={
              item.subject
                ? "min-w-0 break-words text-slate-900"
                : "min-w-0 break-words italic text-slate-500"
            }
          >
            {displaySubject(item.subject)}
          </dd>
        </div>
        {sent ? (
          <div>
            <dt className="text-slate-500">Sent</dt>
            <dd>{sent}</dd>
          </div>
        ) : null}
        {received ? (
          <div>
            <dt className="text-slate-500">Received</dt>
            <dd>{received}</dd>
          </div>
        ) : null}
      </dl>
      {children}
    </aside>
  );
}
