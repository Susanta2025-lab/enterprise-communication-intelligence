import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import type {
  BusinessContextCreateRequest,
  BusinessContextStatus,
  BusinessContextType,
  BusinessContextUpdateRequest,
  ListContextsQuery,
} from "../api/contexts";

export const CONTEXTS_QUERY_KEY = ["contexts"] as const;

export function contextDetailQueryKey(contextId: string) {
  return ["contexts", contextId] as const;
}

export function contextCommunicationsQueryKey(contextId: string) {
  return ["contexts", contextId, "communications"] as const;
}

export function contextTimelineQueryKey(contextId: string) {
  return ["contexts", contextId, "timeline"] as const;
}

export function useContexts(
  apiClient: EciApiClient,
  enabled: boolean,
  filters: Pick<ListContextsQuery, "status" | "type" | "includeArchived"> = {},
) {
  return useQuery({
    queryKey: [...CONTEXTS_QUERY_KEY, filters],
    queryFn: () =>
      apiClient.listContexts({
        limit: 50,
        offset: 0,
        status: filters.status,
        type: filters.type,
        includeArchived: filters.includeArchived,
      }),
    enabled,
  });
}

export function useContextDetail(apiClient: EciApiClient, contextId: string, enabled: boolean) {
  return useQuery({
    queryKey: contextDetailQueryKey(contextId),
    queryFn: () => apiClient.getContext(contextId),
    enabled: enabled && Boolean(contextId),
  });
}

export function useContextCommunications(
  apiClient: EciApiClient,
  contextId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: contextCommunicationsQueryKey(contextId),
    queryFn: () => apiClient.listContextCommunications(contextId, { limit: 50, offset: 0 }),
    enabled: enabled && Boolean(contextId),
  });
}

export function useContextTimeline(apiClient: EciApiClient, contextId: string, enabled: boolean) {
  return useQuery({
    queryKey: contextTimelineQueryKey(contextId),
    queryFn: () => apiClient.getContextTimeline(contextId, { limit: 50, offset: 0 }),
    enabled: enabled && Boolean(contextId),
  });
}

export function useContextMutations(apiClient: EciApiClient) {
  const queryClient = useQueryClient();

  async function invalidateContext(contextId?: string) {
    await queryClient.invalidateQueries({ queryKey: CONTEXTS_QUERY_KEY });
    if (contextId) {
      await queryClient.invalidateQueries({ queryKey: contextDetailQueryKey(contextId) });
      await queryClient.invalidateQueries({
        queryKey: contextCommunicationsQueryKey(contextId),
      });
      await queryClient.invalidateQueries({ queryKey: contextTimelineQueryKey(contextId) });
    }
  }

  const create = useMutation({
    mutationFn: (body: BusinessContextCreateRequest) => apiClient.createContext(body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CONTEXTS_QUERY_KEY });
    },
  });

  const update = useMutation({
    mutationFn: ({
      contextId,
      body,
    }: {
      contextId: string;
      body: BusinessContextUpdateRequest;
    }) => apiClient.updateContext(contextId, body),
    onSuccess: async (context) => {
      await invalidateContext(context.id);
    },
  });

  const archive = useMutation({
    mutationFn: (contextId: string) => apiClient.archiveContext(contextId),
    onSuccess: async (context) => {
      await invalidateContext(context.id);
    },
  });

  const restore = useMutation({
    mutationFn: (contextId: string) => apiClient.restoreContext(contextId),
    onSuccess: async (context) => {
      await invalidateContext(context.id);
    },
  });

  const associate = useMutation({
    mutationFn: ({
      contextId,
      connectorAccountId,
      providerMessageId,
      analysisId,
    }: {
      contextId: string;
      connectorAccountId: string;
      providerMessageId: string;
      analysisId?: string | null;
    }) =>
      apiClient.associateContextCommunication(contextId, {
        connector_account_id: connectorAccountId,
        provider_message_id: providerMessageId,
        analysis_id: analysisId,
      }),
    onSuccess: async (_link, variables) => {
      await queryClient.invalidateQueries({
        queryKey: contextCommunicationsQueryKey(variables.contextId),
      });
      await queryClient.invalidateQueries({
        queryKey: contextTimelineQueryKey(variables.contextId),
      });
    },
  });

  const suggest = useMutation({
    mutationFn: ({
      connectorAccountId,
      providerMessageId,
      analysisId,
    }: {
      connectorAccountId: string;
      providerMessageId: string;
      analysisId: string;
    }) =>
      apiClient.suggestContextAssociations({
        connector_account_id: connectorAccountId,
        provider_message_id: providerMessageId,
        analysis_id: analysisId,
      }),
  });

  const removeAssociation = useMutation({
    mutationFn: ({ contextId, linkId }: { contextId: string; linkId: string }) =>
      apiClient.removeContextCommunication(contextId, linkId),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({
        queryKey: contextCommunicationsQueryKey(variables.contextId),
      });
      await queryClient.invalidateQueries({
        queryKey: contextTimelineQueryKey(variables.contextId),
      });
    },
  });

  return { create, update, archive, restore, associate, suggest, removeAssociation };
}

export type ContextListFilters = {
  status: BusinessContextStatus | "all";
  type: BusinessContextType | "all";
};
