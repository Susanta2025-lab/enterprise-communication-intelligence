import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { EciApiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { hasAllPermissions, hasPermission } from "../auth/permissions";
import { ConfirmDialog } from "../components/connectors/ConfirmDialog";
import { LoadingSkeleton } from "../components/connectors/LoadingSkeleton";
import { ContextFormFields } from "../components/contexts/ContextFormFields";
import {
  ARCHIVE_COPY,
  REMOVE_ASSOCIATION_COPY,
  RESTORE_COPY,
  contextStatusLabel,
  contextTypeLabel,
  timelineEventLabel,
} from "../components/contexts/copy";
import { ProductErrorState } from "../components/feedback/ProductErrorState";
import { Button } from "../components/ui/button";
import { REFRESH_LABEL } from "../errors/copy";
import { presentProductError } from "../errors/presentProductError";
import {
  useContextCommunications,
  useContextDetail,
  useContextMutations,
  useContextTimeline,
} from "../hooks/useContexts";
import { formatMailboxTimestamp } from "../lib/formatTimestamp";
import { CONTEXTS_PATH, DASHBOARD_PATH, mailboxWorkspacePath } from "../navigation/paths";

type ContextWorkspacePageProps = {
  apiClient: EciApiClient;
  contextId: string;
};

type WorkspaceTab = "overview" | "communications" | "timeline";

export function ContextWorkspacePage({ apiClient, contextId }: ContextWorkspacePageProps) {
  const { permissions } = useAuth();
  const canAnalyze = hasPermission(permissions, "communications:analyze");
  const canAssociate = hasAllPermissions(permissions, [
    "communications:read",
    "communications:analyze",
  ]);
  const [tab, setTab] = useState<WorkspaceTab>("overview");
  const [editing, setEditing] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [removeError, setRemoveError] = useState<unknown>(null);
  const [pendingArchive, setPendingArchive] = useState(false);
  const [pendingRestore, setPendingRestore] = useState(false);
  const [pendingRemoveLinkId, setPendingRemoveLinkId] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const mutations = useContextMutations(apiClient);

  const detailQuery = useContextDetail(apiClient, contextId, canAnalyze);
  const linksQuery = useContextCommunications(
    apiClient,
    contextId,
    canAssociate && tab === "communications",
  );
  const timelineQuery = useContextTimeline(
    apiClient,
    contextId,
    canAnalyze && tab === "timeline",
  );

  const context = detailQuery.data;
  const mutatePresentation = actionError
    ? presentProductError("context_mutate", actionError)
    : null;
  const removePresentation = removeError
    ? presentProductError("context_disassociate", removeError)
    : null;
  const detailError = detailQuery.isError
    ? presentProductError("context_get", detailQuery.error)
    : null;
  const linksError = linksQuery.isError
    ? presentProductError("context_communications", linksQuery.error)
    : null;
  const timelineError = timelineQuery.isError
    ? presentProductError("context_timeline", timelineQuery.error)
    : null;

  useEffect(() => {
    if (detailQuery.isError || actionError || removeError) {
      errorRef.current?.focus();
    }
  }, [detailQuery.isError, actionError, removeError]);

  if (!canAnalyze) {
    return (
      <ProductErrorState
        message="Opening a context requires the communications:analyze permission."
        retryLabel={null}
        showSignIn={false}
        showDashboardLink
      />
    );
  }

  return (
    <section className="space-y-6" aria-labelledby="context-workspace-heading">
      <nav className="text-sm">
        <Link to={DASHBOARD_PATH} className="font-medium text-slate-700 underline">
          Dashboard
        </Link>
        <span className="mx-2 text-slate-400" aria-hidden="true">
          /
        </span>
        <Link to={CONTEXTS_PATH} className="font-medium text-slate-700 underline">
          Contexts
        </Link>
        <span className="mx-2 text-slate-400" aria-hidden="true">
          /
        </span>
        <span className="text-slate-500">Workspace</span>
      </nav>

      {detailQuery.isPending ? <LoadingSkeleton /> : null}
      {detailError ? (
        <div ref={errorRef} tabIndex={-1}>
          <ProductErrorState {...detailError} onRetry={() => void detailQuery.refetch()} />
        </div>
      ) : null}
      {mutatePresentation ? (
        <div ref={errorRef} tabIndex={-1}>
          <ProductErrorState {...mutatePresentation} />
        </div>
      ) : null}
      {removePresentation ? (
        <div ref={errorRef} tabIndex={-1}>
          <ProductErrorState {...removePresentation} />
        </div>
      ) : null}

      {context ? (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  id="context-workspace-heading"
                  className="text-lg font-semibold text-slate-900"
                >
                  {context.title}
                </h2>
                <span
                  className={
                    context.status === "archived"
                      ? "rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-900"
                      : "rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-900"
                  }
                >
                  {contextStatusLabel(context.status)}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                {contextTypeLabel(context.type)}
                {context.reference ? ` · ${context.reference}` : ""}
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              {context.status === "active" ? (
                <>
                  <Button
                    className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
                    onClick={() => {
                      setEditing((value) => !value);
                      setActionError(null);
                    }}
                  >
                    {editing ? "Close editor" : "Edit"}
                  </Button>
                  <Button
                    className="w-full sm:w-auto"
                    onClick={() => setPendingArchive(true)}
                    disabled={mutations.archive.isPending}
                  >
                    Archive
                  </Button>
                </>
              ) : (
                <Button
                  className="w-full sm:w-auto"
                  onClick={() => setPendingRestore(true)}
                  disabled={mutations.restore.isPending}
                >
                  Restore
                </Button>
              )}
              <Button
                className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
                onClick={() => void detailQuery.refetch()}
                disabled={detailQuery.isFetching}
              >
                {REFRESH_LABEL}
              </Button>
            </div>
          </div>

          {editing && context.status === "active" ? (
            <div className="rounded-lg border border-slate-200 bg-white p-5">
              <h3 className="text-base font-semibold text-slate-900">Edit context</h3>
              <ContextFormFields
                initial={{
                  type: context.type,
                  title: context.title,
                  description: context.description ?? "",
                  reference: context.reference ?? "",
                }}
                submitLabel="Save"
                busy={mutations.update.isPending}
                onCancel={() => setEditing(false)}
                onSubmit={async (values) => {
                  setActionError(null);
                  try {
                    await mutations.update.mutateAsync({
                      contextId: context.id,
                      body: values,
                    });
                    setEditing(false);
                  } catch (error) {
                    setActionError(error);
                  }
                }}
              />
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2" role="tablist">
            {(
              [
                ["overview", "Overview"],
                ["communications", "Communications"],
                ["timeline", "Timeline"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className={
                  tab === id
                    ? "min-h-11 rounded-md bg-slate-900 px-4 text-sm font-medium text-white"
                    : "min-h-11 rounded-md px-4 text-sm font-medium text-slate-700 hover:bg-slate-100"
                }
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "overview" ? (
            <dl className="grid gap-4 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-2">
              <div>
                <dt className="text-sm text-slate-500">Type</dt>
                <dd className="text-sm font-medium text-slate-900">
                  {contextTypeLabel(context.type)}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-slate-500">Status</dt>
                <dd className="text-sm font-medium text-slate-900">
                  {contextStatusLabel(context.status)}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm text-slate-500">Description</dt>
                <dd className="text-sm text-slate-900">
                  {context.description?.trim() ? context.description : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-slate-500">Reference</dt>
                <dd className="text-sm text-slate-900">{context.reference ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-sm text-slate-500">Created</dt>
                <dd className="text-sm text-slate-900">
                  {formatMailboxTimestamp(context.created_at) ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-slate-500">Updated</dt>
                <dd className="text-sm text-slate-900">
                  {formatMailboxTimestamp(context.updated_at) ?? "—"}
                </dd>
              </div>
              {context.archived_at ? (
                <div>
                  <dt className="text-sm text-slate-500">Archived</dt>
                  <dd className="text-sm text-slate-900">
                    {formatMailboxTimestamp(context.archived_at) ?? "—"}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}

          {tab === "communications" ? (
            <div className="space-y-4">
              {!canAssociate ? (
                <ProductErrorState
                  message="Listing associations requires communications:read and communications:analyze."
                  retryLabel={null}
                  showSignIn={false}
                  showDashboardLink={false}
                />
              ) : null}
              {canAssociate && linksQuery.isPending ? <LoadingSkeleton /> : null}
              {linksError ? (
                <ProductErrorState {...linksError} onRetry={() => void linksQuery.refetch()} />
              ) : null}
              {canAssociate &&
              !linksQuery.isPending &&
              !linksQuery.isError &&
              (linksQuery.data?.items.length ?? 0) === 0 ? (
                <div
                  className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center"
                  data-testid="context-communications-empty"
                >
                  <p className="text-sm font-medium text-slate-900">No linked communications</p>
                  <p className="mt-1 text-sm text-slate-600">
                    Open a mailbox message and use Add to Context to associate it explicitly.
                  </p>
                </div>
              ) : null}
              {canAssociate && (linksQuery.data?.items.length ?? 0) > 0 ? (
                <ul className="space-y-3" aria-label="Linked communications">
                  {linksQuery.data?.items.map((link) => (
                    <li
                      key={link.id}
                      className="rounded-lg border border-slate-200 bg-white p-4"
                      data-testid={`context-link-${link.id}`}
                    >
                      <dl className="space-y-2 text-sm">
                        <div>
                          <dt className="text-slate-500">Provider message id</dt>
                          <dd className="break-all font-medium text-slate-900">
                            {link.provider_message_id}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">Connector account</dt>
                          <dd className="break-all text-slate-900">{link.connector_account_id}</dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">Associated</dt>
                          <dd>{formatMailboxTimestamp(link.associated_at) ?? "—"}</dd>
                        </div>
                      </dl>
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                        <Link
                          to={mailboxWorkspacePath(link.connector_account_id)}
                          className="inline-flex min-h-11 items-center justify-center rounded-md px-4 text-sm font-medium text-slate-700 underline"
                        >
                          Open mailbox
                        </Link>
                        <Button
                          className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
                          onClick={() => setPendingRemoveLinkId(link.id)}
                        >
                          Remove from Context
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {tab === "timeline" ? (
            <div className="space-y-4">
              {timelineQuery.isPending ? <LoadingSkeleton /> : null}
              {timelineError ? (
                <ProductErrorState
                  {...timelineError}
                  onRetry={() => void timelineQuery.refetch()}
                />
              ) : null}
              {!timelineQuery.isPending &&
              !timelineQuery.isError &&
              (timelineQuery.data?.items.length ?? 0) === 0 ? (
                <div
                  className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center"
                  data-testid="context-timeline-empty"
                >
                  <p className="text-sm font-medium text-slate-900">No timeline events</p>
                  <p className="mt-1 text-sm text-slate-600">
                    Events appear from durable context, association, analysis, and workflow records.
                  </p>
                </div>
              ) : null}
              {(timelineQuery.data?.items.length ?? 0) > 0 ? (
                <ol className="space-y-3" aria-label="Context timeline">
                  {timelineQuery.data?.items.map((entry) => (
                    <li
                      key={entry.id}
                      className="rounded-lg border border-slate-200 bg-white p-4"
                      data-testid={`timeline-entry-${entry.type}`}
                    >
                      <p className="text-sm font-semibold text-slate-900">
                        {entry.title || timelineEventLabel(entry.type)}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
                        {timelineEventLabel(entry.type)}
                      </p>
                      {entry.summary ? (
                        <p className="mt-2 text-sm text-slate-600">{entry.summary}</p>
                      ) : null}
                      <p className="mt-2 text-xs text-slate-500">
                        {formatMailboxTimestamp(entry.occurred_at) ?? "—"}
                      </p>
                    </li>
                  ))}
                </ol>
              ) : null}
              <p className="text-xs text-slate-500">
                Timeline is a read model. Archive/restore history is limited to the current archived
                state when present.
              </p>
            </div>
          ) : null}
        </>
      ) : null}

      <ConfirmDialog
        open={pendingArchive}
        title="Archive context?"
        description={ARCHIVE_COPY}
        confirmLabel="Archive"
        confirmBusy={mutations.archive.isPending}
        onCancel={() => setPendingArchive(false)}
        onConfirm={() => {
          void (async () => {
            setActionError(null);
            try {
              await mutations.archive.mutateAsync(contextId);
              setPendingArchive(false);
            } catch (error) {
              setActionError(error);
              setPendingArchive(false);
            }
          })();
        }}
      />
      <ConfirmDialog
        open={pendingRestore}
        title="Restore context?"
        description={RESTORE_COPY}
        confirmLabel="Restore"
        confirmBusy={mutations.restore.isPending}
        onCancel={() => setPendingRestore(false)}
        onConfirm={() => {
          void (async () => {
            setActionError(null);
            try {
              await mutations.restore.mutateAsync(contextId);
              setPendingRestore(false);
            } catch (error) {
              setActionError(error);
              setPendingRestore(false);
            }
          })();
        }}
      />
      <ConfirmDialog
        open={pendingRemoveLinkId !== null}
        title="Remove from Context?"
        description={REMOVE_ASSOCIATION_COPY}
        confirmLabel="Remove from Context"
        confirmBusy={mutations.removeAssociation.isPending}
        onCancel={() => setPendingRemoveLinkId(null)}
        onConfirm={() => {
          if (!pendingRemoveLinkId) {
            return;
          }
          void (async () => {
            setRemoveError(null);
            try {
              await mutations.removeAssociation.mutateAsync({
                contextId,
                linkId: pendingRemoveLinkId,
              });
              setPendingRemoveLinkId(null);
            } catch (error) {
              setRemoveError(error);
              setPendingRemoveLinkId(null);
            }
          })();
        }}
      />
    </section>
  );
}
