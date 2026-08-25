export const MAILBOX_UI_PAGE_SIZE = 10;

export type MailboxMessageListItem = {
  provider_message_id: string;
  sender: string;
  subject: string | null;
  sent_at: string | null;
  received_at: string | null;
};

export type MailboxMessageListResponse = {
  items: readonly MailboxMessageListItem[];
  next_cursor: string | null;
};

export type ListMailboxMessagesQuery = {
  connectorAccountId: string;
  pageSize?: number;
  cursor?: string;
};

export function connectorAccountMessagesPath(connectorAccountId: string): string {
  return `/api/v1/connector-accounts/${connectorAccountId}/messages`;
}
