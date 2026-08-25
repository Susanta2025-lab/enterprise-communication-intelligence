import type { MailboxMessageListItem } from "../../api/mailbox";
import { MessageListItem } from "./MessageListItem";

type MessageListProps = {
  items: readonly MailboxMessageListItem[];
  selectedId: string | null;
  onSelect: (item: MailboxMessageListItem) => void;
  busy: boolean;
};

export function MessageList({ items, selectedId, onSelect, busy }: MessageListProps) {
  return (
    <ul aria-label="Recent messages" aria-busy={busy} className="space-y-2">
      {items.map((item) => (
        <MessageListItem
          key={item.provider_message_id}
          item={item}
          selected={item.provider_message_id === selectedId}
          onSelect={() => onSelect(item)}
        />
      ))}
    </ul>
  );
}
