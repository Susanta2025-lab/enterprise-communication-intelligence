import { useQuery, type QueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";

export function mailboxAttachmentsQueryKey(
  connectorAccountId: string,
  providerMessageId: string,
) {
  return ["mailbox-attachments", connectorAccountId, providerMessageId] as const;
}

export function useMailboxAttachments(
  apiClient: EciApiClient,
  connectorAccountId: string,
  providerMessageId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: mailboxAttachmentsQueryKey(connectorAccountId, providerMessageId ?? ""),
    queryFn: () =>
      apiClient.listMailboxAttachments({
        connectorAccountId,
        providerMessageId: providerMessageId ?? "",
      }),
    enabled: enabled && Boolean(connectorAccountId) && Boolean(providerMessageId),
    retry: false,
    refetchOnReconnect: false,
  });
}

export function clearMailboxAttachmentQueries(queryClient: QueryClient): void {
  void queryClient.removeQueries({ queryKey: ["mailbox-attachments"] });
}
