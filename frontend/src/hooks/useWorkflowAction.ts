import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { EciApiClient } from "../api/client";
import { EciApiError } from "../api/errors";
import type { WorkflowActionResponse } from "../api/workflowActions";
import { CONNECTOR_ACCOUNT_QUERY_KEY } from "./useConnectorAccounts";

export type WorkflowMutationOperation = "propose" | "approve" | "reject" | "execute" | "refresh";

type WorkflowError = {
  operation: WorkflowMutationOperation;
  error: unknown;
};

function shouldRefreshAfterFailure(error: unknown): boolean {
  return error instanceof EciApiError && [409, 500, 503].includes(error.status);
}

function isExecuteUncertainty(error: unknown, status: WorkflowActionResponse["status"]): boolean {
  if (!(error instanceof EciApiError) || error.status !== 503) {
    return false;
  }
  return status === "executing";
}

export function useWorkflowAction(apiClient: EciApiClient, analysisId: string | null) {
  const queryClient = useQueryClient();
  const analysisIdRef = useRef(analysisId);
  analysisIdRef.current = analysisId;
  const [action, setAction] = useState<WorkflowActionResponse | null>(null);
  const [executionUncertain, setExecutionUncertain] = useState(false);
  const [lastError, setLastError] = useState<WorkflowError | null>(null);
  const executeInFlight = useRef(false);
  const executeAnalysisIdRef = useRef<string | null>(null);
  const actionIdRef = useRef<string | null>(null);
  actionIdRef.current = action?.id ?? null;

  function belongsToCurrentAnalysis(next: WorkflowActionResponse): boolean {
    return next.analysis_id === analysisIdRef.current;
  }

  function applyAction(next: WorkflowActionResponse): void {
    if (!belongsToCurrentAnalysis(next)) {
      return;
    }
    setAction(next);
  }

  async function refreshOwnedAction(
    actionId: string,
    error: unknown,
  ): Promise<WorkflowActionResponse | null> {
    try {
      const refreshed = await apiClient.getWorkflowAction(actionId);
      applyAction(refreshed);
      setExecutionUncertain(isExecuteUncertainty(error, refreshed.status));
      return refreshed;
    } catch {
      if (error instanceof EciApiError && error.status === 503) {
        setExecutionUncertain(true);
      }
      return null;
    }
  }

  const proposeMutation = useMutation({
    mutationFn: (targetAnalysisId: string) =>
      apiClient.createWorkflowAction({ analysisId: targetAnalysisId }),
    retry: false,
    onMutate: () => {
      setLastError(null);
    },
    onSuccess: (result, targetAnalysisId) => {
      if (targetAnalysisId === analysisIdRef.current) {
        applyAction(result);
        setExecutionUncertain(false);
      }
    },
    onError: (error, targetAnalysisId) => {
      if (targetAnalysisId === analysisIdRef.current) {
        setLastError({ operation: "propose", error });
      }
    },
  });

  const approveMutation = useMutation({
    mutationFn: (actionId: string) => apiClient.approveWorkflowAction(actionId),
    retry: false,
    onMutate: () => {
      setLastError(null);
    },
    onSuccess: applyAction,
    onError: (error, actionId) => {
      if (actionId !== actionIdRef.current) {
        return;
      }
      setLastError({ operation: "approve", error });
      if (shouldRefreshAfterFailure(error)) {
        void refreshOwnedAction(actionId, error);
      }
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (actionId: string) => apiClient.rejectWorkflowAction(actionId),
    retry: false,
    onMutate: () => {
      setLastError(null);
    },
    onSuccess: applyAction,
    onError: (error, actionId) => {
      if (actionId !== actionIdRef.current) {
        return;
      }
      setLastError({ operation: "reject", error });
      if (shouldRefreshAfterFailure(error)) {
        void refreshOwnedAction(actionId, error);
      }
    },
  });

  const executeMutation = useMutation({
    mutationFn: (actionId: string) => apiClient.executeWorkflowAction(actionId),
    retry: false,
    onMutate: () => {
      setLastError(null);
      setExecutionUncertain(false);
      executeAnalysisIdRef.current = analysisIdRef.current;
    },
    onSuccess: (result) => {
      applyAction(result);
      setExecutionUncertain(false);
    },
    onError: (error, actionId) => {
      if (executeAnalysisIdRef.current !== analysisIdRef.current) {
        return;
      }
      setLastError({ operation: "execute", error });
      if (error instanceof EciApiError && error.status === 503) {
        setExecutionUncertain(true);
      }
      if (error instanceof EciApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: CONNECTOR_ACCOUNT_QUERY_KEY });
      }
      if (shouldRefreshAfterFailure(error)) {
        void refreshOwnedAction(actionId, error);
      }
    },
    onSettled: () => {
      executeInFlight.current = false;
    },
  });

  const refreshMutation = useMutation({
    mutationFn: (actionId: string) => apiClient.getWorkflowAction(actionId),
    retry: false,
    onMutate: () => {
      setLastError(null);
    },
    onSuccess: (result) => {
      applyAction(result);
      setExecutionUncertain(result.status === "executing");
    },
    onError: (error, actionId) => {
      if (actionId !== actionIdRef.current) {
        return;
      }
      setLastError({ operation: "refresh", error });
    },
  });

  const proposeReset = proposeMutation.reset;
  const approveReset = approveMutation.reset;
  const rejectReset = rejectMutation.reset;
  const executeReset = executeMutation.reset;
  const refreshReset = refreshMutation.reset;

  useEffect(() => {
    setAction(null);
    setExecutionUncertain(false);
    setLastError(null);
    executeInFlight.current = false;
    proposeReset();
    approveReset();
    rejectReset();
    executeReset();
    refreshReset();
  }, [analysisId, proposeReset, approveReset, rejectReset, executeReset, refreshReset]);

  const actionForSelection =
    action !== null && action.analysis_id === analysisId ? action : null;

  return {
    action: actionForSelection,
    executionUncertain: actionForSelection !== null && executionUncertain,
    error: lastError?.error ?? null,
    errorOperation: lastError?.operation ?? null,
    proposePending: proposeMutation.isPending,
    approvePending: approveMutation.isPending,
    rejectPending: rejectMutation.isPending,
    executePending: executeMutation.isPending,
    refreshPending: refreshMutation.isPending,
    propose: () => {
      if (!analysisId || proposeMutation.isPending || actionForSelection !== null) {
        return;
      }
      proposeMutation.mutate(analysisId);
    },
    approve: () => {
      if (!actionForSelection || approveMutation.isPending) {
        return;
      }
      approveMutation.mutate(actionForSelection.id);
    },
    reject: () => {
      if (!actionForSelection || rejectMutation.isPending) {
        return;
      }
      rejectMutation.mutate(actionForSelection.id);
    },
    execute: () => {
      if (!actionForSelection || executeInFlight.current || executeMutation.isPending) {
        return;
      }
      executeInFlight.current = true;
      executeMutation.mutate(actionForSelection.id);
    },
    refresh: () => {
      if (!actionForSelection || refreshMutation.isPending) {
        return;
      }
      refreshMutation.mutate(actionForSelection.id);
    },
  };
}
