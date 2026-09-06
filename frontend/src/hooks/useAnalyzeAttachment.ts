import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { EciApiClient } from "../api/client";
import type { AttachmentAnalysisResponse } from "../api/attachments";
import { EciApiError } from "../api/errors";
import { attachmentAnalysesQueryKey } from "./useAttachmentAnalysisHistory";
import { CONNECTOR_ACCOUNT_QUERY_KEY } from "./useConnectorAccounts";

type AnalyzeAttachmentState = {
  pendingId: string | null;
  results: Record<string, AttachmentAnalysisResponse>;
  errors: Record<string, unknown>;
};

export function useAnalyzeAttachment(
  apiClient: EciApiClient,
  connectorAccountId: string,
  providerMessageId: string | null,
) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AnalyzeAttachmentState>({
    pendingId: null,
    results: {},
    errors: {},
  });

  useEffect(() => {
    setState({ pendingId: null, results: {}, errors: {} });
  }, [connectorAccountId, providerMessageId]);

  async function analyze(providerAttachmentId: string): Promise<void> {
    if (!providerMessageId || state.pendingId === providerAttachmentId) {
      return;
    }
    setState((current) => {
      const errors = { ...current.errors };
      delete errors[providerAttachmentId];
      return { ...current, pendingId: providerAttachmentId, errors };
    });
    try {
      const result = await apiClient.analyzeMailboxAttachment({
        connectorAccountId,
        providerMessageId,
        providerAttachmentId,
      });
      setState((current) => ({
        pendingId: current.pendingId === providerAttachmentId ? null : current.pendingId,
        results: { ...current.results, [providerAttachmentId]: result },
        errors: current.errors,
      }));
      void queryClient.invalidateQueries({
        queryKey: attachmentAnalysesQueryKey(connectorAccountId, providerMessageId),
      });
    } catch (error) {
      if (error instanceof EciApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: CONNECTOR_ACCOUNT_QUERY_KEY });
      }
      setState((current) => ({
        pendingId: current.pendingId === providerAttachmentId ? null : current.pendingId,
        results: current.results,
        errors: { ...current.errors, [providerAttachmentId]: error },
      }));
    }
  }

  return {
    analyze,
    pendingId: state.pendingId,
    resultFor: (providerAttachmentId: string) => state.results[providerAttachmentId] ?? null,
    errorFor: (providerAttachmentId: string) => state.errors[providerAttachmentId] ?? null,
  };
}
