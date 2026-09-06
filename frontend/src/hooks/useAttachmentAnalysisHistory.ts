import { useQuery, type QueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import type { AttachmentAnalysisResponse } from "../api/attachments";

export function attachmentAnalysesQueryKey(
  connectorAccountId: string,
  providerMessageId: string,
) {
  return ["attachment-analyses", connectorAccountId, providerMessageId] as const;
}

export function useAttachmentAnalysisHistory(
  apiClient: EciApiClient,
  connectorAccountId: string,
  providerMessageId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: attachmentAnalysesQueryKey(connectorAccountId, providerMessageId ?? ""),
    queryFn: () =>
      apiClient.listAttachmentAnalyses({
        connectorAccountId,
        providerMessageId: providerMessageId ?? "",
        limit: 20,
        offset: 0,
      }),
    enabled: enabled && Boolean(connectorAccountId) && Boolean(providerMessageId),
    retry: false,
    refetchOnReconnect: false,
  });
}

export function latestAnalysisByAttachment(
  items: readonly AttachmentAnalysisResponse[] | undefined,
): Map<string, AttachmentAnalysisResponse> {
  const latest = new Map<string, AttachmentAnalysisResponse>();
  for (const item of items ?? []) {
    if (!latest.has(item.provider_attachment_id)) {
      latest.set(item.provider_attachment_id, item);
    }
  }
  return latest;
}

export function previousAnalysesForAttachment(
  items: readonly AttachmentAnalysisResponse[] | undefined,
  providerAttachmentId: string,
): AttachmentAnalysisResponse[] {
  return (items ?? []).filter((item) => item.provider_attachment_id === providerAttachmentId);
}

export function clearAttachmentAnalysisQueries(queryClient: QueryClient): void {
  void queryClient.removeQueries({ queryKey: ["attachment-analyses"] });
}
