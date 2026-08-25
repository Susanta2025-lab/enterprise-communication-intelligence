import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { EciApiClient } from "../api/client";
import { EciApiError } from "../api/errors";
import type { CommunicationAnalysisResponse } from "../api/mailbox";
import { CONNECTOR_ACCOUNT_QUERY_KEY } from "./useConnectorAccounts";

type AnalysisSession = {
  providerMessageId: string;
  result: CommunicationAnalysisResponse;
};

export function useAnalyzeMailboxMessage(
  apiClient: EciApiClient,
  connectorAccountId: string,
  selectedProviderMessageId: string | null,
) {
  const queryClient = useQueryClient();
  const selectedIdRef = useRef(selectedProviderMessageId);
  selectedIdRef.current = selectedProviderMessageId;
  const [session, setSession] = useState<AnalysisSession | null>(null);

  const mutation = useMutation({
    mutationFn: (providerMessageId: string) =>
      apiClient.analyzeMailboxMessage({
        connectorAccountId,
        providerMessageId,
      }),
    retry: false,
    onSuccess: (result, providerMessageId) => {
      if (providerMessageId === selectedIdRef.current) {
        setSession({ providerMessageId, result });
      }
    },
    onError: (error, providerMessageId) => {
      if (providerMessageId !== selectedIdRef.current) {
        return;
      }
      if (error instanceof EciApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: CONNECTOR_ACCOUNT_QUERY_KEY });
      }
    },
  });

  const resetMutation = mutation.reset;
  useEffect(() => {
    setSession(null);
    resetMutation();
  }, [selectedProviderMessageId, connectorAccountId, resetMutation]);

  const belongsToSelection = mutation.variables === selectedProviderMessageId;
  const result =
    session?.providerMessageId === selectedProviderMessageId ? session.result : null;

  function resetAnalysis(): void {
    setSession(null);
    resetMutation();
  }

  return {
    analyze: (providerMessageId: string) => {
      mutation.mutate(providerMessageId);
    },
    isPending: belongsToSelection && mutation.isPending,
    result,
    error: belongsToSelection && mutation.isError ? mutation.error : null,
    resetAnalysis,
  };
}
