import { useState } from "react";

import type { EciApiClient } from "../../api/client";
import type { ContextSuggestionItem } from "../../api/contexts";
import { useAuth } from "../../auth/AuthContext";
import { hasAllPermissions } from "../../auth/permissions";
import { ProductErrorState } from "../feedback/ProductErrorState";
import { Button } from "../ui/button";
import { presentProductError } from "../../errors/presentProductError";
import { useContextMutations, useContexts } from "../../hooks/useContexts";
import { contextTypeLabel } from "./copy";

type AddToContextPanelProps = {
  apiClient: EciApiClient;
  connectorAccountId: string;
  providerMessageId: string;
  analysisId?: string | null;
};

function matchStrengthLabel(strength: ContextSuggestionItem["match_strength"]): string {
  if (strength === "high") {
    return "High match";
  }
  if (strength === "medium") {
    return "Medium match";
  }
  return "Low match";
}

export function AddToContextPanel({
  apiClient,
  connectorAccountId,
  providerMessageId,
  analysisId = null,
}: AddToContextPanelProps) {
  const { permissions } = useAuth();
  const canAssociate = hasAllPermissions(permissions, [
    "communications:read",
    "communications:analyze",
  ]);
  const [open, setOpen] = useState(false);
  const [selectedContextId, setSelectedContextId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [suggestError, setSuggestError] = useState<unknown>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<ContextSuggestionItem[] | null>(null);
  const [noMatchReason, setNoMatchReason] = useState<string | null>(null);
  const contextsQuery = useContexts(apiClient, canAssociate && open, { status: "active" });
  const mutations = useContextMutations(apiClient);

  if (!canAssociate) {
    return null;
  }

  const errorPresentation = error ? presentProductError("context_associate", error) : null;
  const suggestErrorPresentation = suggestError
    ? presentProductError("context_suggest", suggestError)
    : null;
  const activeContexts = contextsQuery.data?.items ?? [];
  const canSuggest = Boolean(analysisId);

  async function associateSelected(contextId: string) {
    setError(null);
    setSuccess(null);
    try {
      await mutations.associate.mutateAsync({
        contextId,
        connectorAccountId,
        providerMessageId,
        analysisId,
      });
      setSuccess("Communication associated with the selected context.");
      setSelectedContextId(contextId);
    } catch (associateError) {
      setError(associateError);
    }
  }

  return (
    <div className="mt-4 border-t border-slate-200 pt-4" data-testid="add-to-context-panel">
      <Button
        className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
        onClick={() => {
          setOpen((value) => !value);
          setError(null);
          setSuggestError(null);
          setSuccess(null);
          setSuggestions(null);
          setNoMatchReason(null);
        }}
      >
        {open ? "Close Add to Context" : "Add to Context"}
      </Button>
      {open ? (
        <div className="mt-3 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-600">
            Review AI suggestions if available, then explicitly associate this message with a
            context. Suggestions are proposals only and do not create an association until you
            confirm.
          </p>

          {canSuggest ? (
            <div className="space-y-2" data-testid="context-suggest-section">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
                  disabled={mutations.suggest.isPending || mutations.associate.isPending}
                  aria-busy={mutations.suggest.isPending}
                  onClick={() => {
                    void (async () => {
                      if (!analysisId) {
                        return;
                      }
                      setSuggestError(null);
                      setNoMatchReason(null);
                      setSuggestions(null);
                      try {
                        const result = await mutations.suggest.mutateAsync({
                          connectorAccountId,
                          providerMessageId,
                          analysisId,
                        });
                        setSuggestions(result.suggestions);
                        setNoMatchReason(result.no_match_reason);
                      } catch (requestError) {
                        setSuggestError(requestError);
                        setSuggestions(null);
                        setNoMatchReason(null);
                      }
                    })();
                  }}
                >
                  {mutations.suggest.isPending ? "Suggesting…" : "Suggest Context"}
                </Button>
                <span className="text-xs text-slate-500">AI suggestion · review before associating</span>
              </div>
              {mutations.suggest.isPending ? (
                <p className="text-sm text-slate-600" role="status">
                  Loading AI suggestions…
                </p>
              ) : null}
              {suggestErrorPresentation ? (
                <div data-testid="context-suggest-error">
                  <ProductErrorState {...suggestErrorPresentation} />
                  <p className="mt-1 text-sm text-slate-600">
                    You can still choose an active context manually below.
                  </p>
                </div>
              ) : null}
              {suggestions !== null && suggestions.length === 0 ? (
                <p className="text-sm text-slate-600" data-testid="context-suggest-no-match">
                  {noMatchReason ??
                    "No suitable context found. Choose another active context manually, create a new context, or do nothing."}
                </p>
              ) : null}
              {suggestions !== null && suggestions.length > 0 ? (
                <div className="space-y-2" data-testid="context-suggest-list">
                  <p className="text-sm font-medium text-slate-800">Suggested context</p>
                  <ul className="space-y-2">
                    {suggestions.map((item) => (
                      <li
                        key={item.business_context_id}
                        className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="text-sm font-medium text-slate-900">
                            {item.title}{" "}
                            <span className="font-normal text-slate-500">
                              ({contextTypeLabel(item.type)})
                            </span>
                          </p>
                          <p className="text-xs text-slate-600">
                            Possible match · {matchStrengthLabel(item.match_strength)}
                            {item.reference ? ` · ${item.reference}` : ""}
                          </p>
                        </div>
                        <Button
                          className="w-full sm:w-auto"
                          disabled={mutations.associate.isPending}
                          aria-busy={mutations.associate.isPending}
                          onClick={() => {
                            void associateSelected(item.business_context_id);
                          }}
                        >
                          Associate
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-slate-600" data-testid="context-suggest-unavailable">
              Analyze this message first to request AI context suggestions. Manual association
              remains available below.
            </p>
          )}

          <div className="border-t border-slate-200 pt-3">
            <p className="mb-2 text-sm font-medium text-slate-800">All active contexts</p>
            {contextsQuery.isPending ? (
              <p className="text-sm text-slate-600" role="status">
                Loading contexts…
              </p>
            ) : null}
            {contextsQuery.isError ? (
              <ProductErrorState
                {...presentProductError("context_list", contextsQuery.error)}
                onRetry={() => void contextsQuery.refetch()}
              />
            ) : null}
            {!contextsQuery.isPending && !contextsQuery.isError && activeContexts.length === 0 ? (
              <p className="text-sm text-slate-600">
                No active contexts available. Create a context first, then associate this message.
              </p>
            ) : null}
            {activeContexts.length > 0 ? (
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">Active context</span>
                <select
                  className="min-h-11 rounded-md border border-slate-300 bg-white px-3 text-slate-900"
                  value={selectedContextId}
                  onChange={(event) => setSelectedContextId(event.target.value)}
                  disabled={mutations.associate.isPending}
                  data-testid="context-manual-select"
                >
                  <option value="">Select a context</option>
                  {activeContexts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title} ({contextTypeLabel(item.type)})
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {errorPresentation ? <ProductErrorState {...errorPresentation} /> : null}
            {success ? (
              <p className="mt-2 text-sm text-emerald-800" role="status">
                {success}
              </p>
            ) : null}
            <Button
              className="mt-3 w-full sm:w-auto"
              disabled={!selectedContextId || mutations.associate.isPending}
              aria-busy={mutations.associate.isPending}
              onClick={() => {
                void associateSelected(selectedContextId);
              }}
            >
              Associate
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
