import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { EciApiClient } from "../api/client";
import type { BusinessContextStatus, BusinessContextType } from "../api/contexts";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { LoadingSkeleton } from "../components/connectors/LoadingSkeleton";
import { ContextFormFields } from "../components/contexts/ContextFormFields";
import {
  CONTEXT_TYPE_OPTIONS,
  contextStatusLabel,
  contextTypeLabel,
} from "../components/contexts/copy";
import { ProductErrorState } from "../components/feedback/ProductErrorState";
import { Button } from "../components/ui/button";
import { REFRESH_LABEL } from "../errors/copy";
import { presentProductError } from "../errors/presentProductError";
import { useContextMutations, useContexts } from "../hooks/useContexts";
import { formatMailboxTimestamp } from "../lib/formatTimestamp";
import { contextWorkspacePath, DASHBOARD_PATH } from "../navigation/paths";

type ContextsListPageProps = {
  apiClient: EciApiClient;
};

export function ContextsListPage({ apiClient }: ContextsListPageProps) {
  const { permissions } = useAuth();
  const navigate = useNavigate();
  const canAnalyze = hasPermission(permissions, "communications:analyze");
  const [statusFilter, setStatusFilter] = useState<BusinessContextStatus | "all">("active");
  const [typeFilter, setTypeFilter] = useState<BusinessContextType | "all">("all");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const mutations = useContextMutations(apiClient);

  const listQuery = useContexts(apiClient, canAnalyze, {
    status: statusFilter === "all" ? undefined : statusFilter,
    type: typeFilter === "all" ? undefined : typeFilter,
    includeArchived: statusFilter === "all",
  });

  const listError = listQuery.isError
    ? presentProductError("context_list", listQuery.error)
    : null;
  const createPresentation = createError
    ? presentProductError("context_mutate", createError)
    : null;

  if (!canAnalyze) {
    return (
      <section className="space-y-4" aria-labelledby="contexts-heading">
        <h2 id="contexts-heading" className="text-lg font-semibold text-slate-900">
          Contexts
        </h2>
        <ProductErrorState
          message="Viewing contexts requires the communications:analyze permission."
          retryLabel={null}
          showSignIn={false}
          showDashboardLink
        />
      </section>
    );
  }

  return (
    <section className="space-y-6" aria-labelledby="contexts-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <nav className="mb-2 text-sm">
            <Link to={DASHBOARD_PATH} className="font-medium text-slate-700 underline">
              Dashboard
            </Link>
            <span className="mx-2 text-slate-400" aria-hidden="true">
              /
            </span>
            <span className="text-slate-500">Contexts</span>
          </nav>
          <h2 id="contexts-heading" className="text-lg font-semibold text-slate-900">
            Contexts
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Organize communications by matter, case, project, or other business context. A mailbox
            connection is not required to create or manage contexts.
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <Button
            className="w-full sm:w-auto"
            onClick={() => void listQuery.refetch()}
            disabled={listQuery.isFetching}
            aria-busy={listQuery.isFetching && !listQuery.isPending}
          >
            {REFRESH_LABEL}
          </Button>
          <Button
            className="w-full sm:w-auto"
            onClick={() => {
              setCreating(true);
              setCreateError(null);
            }}
          >
            Create context
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Status</span>
          <select
            className="min-h-11 rounded-md border border-slate-300 bg-white px-3 text-slate-900"
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as BusinessContextStatus | "all")
            }
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="all">All</option>
          </select>
        </label>
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Type</span>
          <select
            className="min-h-11 rounded-md border border-slate-300 bg-white px-3 text-slate-900"
            value={typeFilter}
            onChange={(event) =>
              setTypeFilter(event.target.value as BusinessContextType | "all")
            }
          >
            <option value="all">All types</option>
            {CONTEXT_TYPE_OPTIONS.map((type) => (
              <option key={type} value={type}>
                {contextTypeLabel(type)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {creating ? (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h3 className="text-base font-semibold text-slate-900">New context</h3>
          {createPresentation ? <ProductErrorState {...createPresentation} /> : null}
          <ContextFormFields
            submitLabel="Create"
            busy={mutations.create.isPending}
            onCancel={() => {
              setCreating(false);
              setCreateError(null);
            }}
            onSubmit={async (values) => {
              setCreateError(null);
              try {
                const created = await mutations.create.mutateAsync(values);
                setCreating(false);
                navigate(contextWorkspacePath(created.id));
              } catch (error) {
                setCreateError(error);
              }
            }}
          />
        </div>
      ) : null}

      {listQuery.isPending ? <LoadingSkeleton /> : null}
      {listError ? (
        <ProductErrorState {...listError} onRetry={() => void listQuery.refetch()} />
      ) : null}

      {!listQuery.isPending && !listQuery.isError && (listQuery.data?.items.length ?? 0) === 0 ? (
        <div
          className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center"
          data-testid="contexts-empty"
        >
          <p className="text-sm font-medium text-slate-900">No contexts yet</p>
          <p className="mt-1 text-sm text-slate-600">
            Create a project, matter, or case to start organizing communications.
          </p>
        </div>
      ) : null}

      {!listQuery.isPending && !listQuery.isError && (listQuery.data?.items.length ?? 0) > 0 ? (
        <ul className="space-y-3" aria-label="Context list">
          {listQuery.data?.items.map((item) => {
            const updated = formatMailboxTimestamp(item.updated_at);
            return (
              <li key={item.id}>
                <Link
                  to={contextWorkspacePath(item.id)}
                  className="block rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
                  data-testid={`context-card-${item.id}`}
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-slate-900">{item.title}</p>
                      <p className="mt-1 text-sm text-slate-600">
                        {contextTypeLabel(item.type)}
                        {item.reference ? ` · ${item.reference}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
                      <span
                        className={
                          item.status === "archived"
                            ? "rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-900"
                            : "rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-900"
                        }
                      >
                        {contextStatusLabel(item.status)}
                      </span>
                      {updated ? (
                        <span className="text-xs text-slate-500">Updated {updated}</span>
                      ) : null}
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
