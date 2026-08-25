import type { MailboxMessageListItem } from "../../api/mailbox";
import { formatMailboxTimestamp } from "../../lib/formatTimestamp";
import { cn } from "../../lib/utils";
import { displaySubject } from "./copy";

type MessageListItemProps = {
  item: MailboxMessageListItem;
  selected: boolean;
  onSelect: () => void;
};

export function MessageListItem({ item, selected, onSelect }: MessageListItemProps) {
  const timestamp =
    formatMailboxTimestamp(item.received_at) ?? formatMailboxTimestamp(item.sent_at);

  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={cn(
          "w-full rounded-md border px-3 py-3 text-left",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900",
          selected
            ? "border-slate-900 bg-slate-100 shadow-sm"
            : "border-slate-200 bg-white hover:bg-slate-50",
        )}
      >
        <p className="text-sm font-medium text-slate-900">{item.sender}</p>
        <p className={cn("text-sm", item.subject ? "text-slate-800" : "italic text-slate-500")}>
          {displaySubject(item.subject)}
        </p>
        {timestamp ? <p className="mt-1 text-xs text-slate-500">{timestamp}</p> : null}
      </button>
    </li>
  );
}
