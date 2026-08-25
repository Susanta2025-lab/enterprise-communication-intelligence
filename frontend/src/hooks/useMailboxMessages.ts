import {
  useInfiniteQuery,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import {
  MAILBOX_UI_PAGE_SIZE,
  type MailboxMessageListItem,
  type MailboxMessageListResponse,
} from "../api/mailbox";

export function mailboxMessagesQueryKey(connectorAccountId: string) {
  return ["mailbox-messages", connectorAccountId] as const;
}

export function flattenMailboxItems(
  pages: readonly MailboxMessageListResponse[] | undefined,
): MailboxMessageListItem[] {
  if (!pages) {
    return [];
  }
  const seen = new Set<string>();
  const items: MailboxMessageListItem[] = [];
  for (const page of pages) {
    for (const item of page.items) {
      if (seen.has(item.provider_message_id)) {
        continue;
      }
      seen.add(item.provider_message_id);
      items.push(item);
    }
  }
  return items;
}

export async function refreshMailboxMessages(
  queryClient: QueryClient,
  connectorAccountId: string,
): Promise<void> {
  const queryKey = mailboxMessagesQueryKey(connectorAccountId);
  queryClient.setQueryData<InfiniteData<MailboxMessageListResponse, string | undefined>>(
    queryKey,
    (current) => {
      if (!current) {
        return current;
      }
      return {
        pages: current.pages.slice(0, 1),
        pageParams: current.pageParams.slice(0, 1),
      };
    },
  );
  await queryClient.invalidateQueries({ queryKey });
}

export function useMailboxMessages(
  apiClient: EciApiClient,
  connectorAccountId: string,
  enabled: boolean,
) {
  return useInfiniteQuery({
    queryKey: mailboxMessagesQueryKey(connectorAccountId),
    queryFn: ({ pageParam }) =>
      apiClient.listMailboxMessages({
        connectorAccountId,
        pageSize: MAILBOX_UI_PAGE_SIZE,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled,
    retry: false,
    refetchOnReconnect: false,
  });
}
