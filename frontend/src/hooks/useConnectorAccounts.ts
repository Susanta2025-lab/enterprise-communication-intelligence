import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import { navigateToAuthorizationUrl } from "../navigation/external";

export const CONNECTOR_ACCOUNT_QUERY_KEY = ["connector-accounts"] as const;

export function useConnectorAccounts(apiClient: EciApiClient, enabled: boolean) {
  return useQuery({
    queryKey: CONNECTOR_ACCOUNT_QUERY_KEY,
    queryFn: () => apiClient.listConnectorAccounts({ limit: 20, offset: 0 }),
    enabled,
  });
}

export function useConnectorAccountMutations(apiClient: EciApiClient) {
  const queryClient = useQueryClient();

  async function startAuthorization(url: string): Promise<void> {
    if (!navigateToAuthorizationUrl(url)) {
      throw new Error("authorization_url_invalid");
    }
  }

  const gmailConnect = useMutation({
    mutationFn: async () => {
      const result = await apiClient.startGmailAuthorization();
      await startAuthorization(result.authorization_url);
    },
  });

  const microsoftConnect = useMutation({
    mutationFn: async () => {
      const result = await apiClient.startMicrosoftGraphAuthorization();
      await startAuthorization(result.authorization_url);
    },
  });

  const reauthorize = useMutation({
    mutationFn: async (connectorAccountId: string) => {
      const result = await apiClient.reauthorizeConnectorAccount(connectorAccountId);
      await startAuthorization(result.authorization_url);
    },
  });

  const disconnect = useMutation({
    mutationFn: (connectorAccountId: string) => apiClient.disconnectConnectorAccount(connectorAccountId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CONNECTOR_ACCOUNT_QUERY_KEY });
    },
  });

  return { gmailConnect, microsoftConnect, reauthorize, disconnect };
}
