import { useEffect, useState } from "react";

import type { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { ConfirmDialog } from "../components/connectors/ConfirmDialog";
import { ConnectAnotherAccount } from "../components/connectors/ConnectAnotherAccount";
import { ConnectorCard } from "../components/connectors/ConnectorCard";
import { LoadingSkeleton } from "../components/connectors/LoadingSkeleton";
import { OAuthReturnNotice } from "../components/connectors/OAuthReturnNotice";
import { PermissionGate } from "../components/connectors/PermissionGate";
import { providerLabel } from "../components/connectors/copy";
import { ProductErrorState } from "../components/feedback/ProductErrorState";
import { Button } from "../components/ui/button";
import { REFRESH_LABEL } from "../errors/copy";
import { presentProductError } from "../errors/presentProductError";
import { useConnectorAccountMutations, useConnectorAccounts } from "../hooks/useConnectorAccounts";
import { useOAuthReturn } from "../hooks/useOAuthReturn";

type ConnectorDashboardPageProps = {
  apiClient: EciApiClient;
};

export function ConnectorDashboardPage({ apiClient }: ConnectorDashboardPageProps) {
  const { permissions } = useAuth();
  const { notice, shouldRefresh } = useOAuthReturn();
  const query = useConnectorAccounts(apiClient, true);
  const mutations = useConnectorAccountMutations(apiClient);
  const [pendingDisconnect, setPendingDisconnect] = useState<ConnectorAccount | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  const refetch = query.refetch;
  useEffect(() => {
    if (shouldRefresh) {
      void refetch();
    }
  }, [refetch, shouldRefresh]);

  const connectBusy =
    mutations.gmailConnect.isPending ||
    mutations.microsoftConnect.isPending ||
    mutations.gmailConnectAnother.isPending ||
    mutations.microsoftConnectAnother.isPending ||
    mutations.reauthorize.isPending ||
    mutations.disconnect.isPending;

  const items = query.data?.items ?? [];
  const hasGmail = items.some((item) => item.provider === "gmail");
  const hasGraph = items.some((item) => item.provider === "microsoft_graph");
  const canConnect = hasPermission(permissions, "communications:connect");
  const listError = query.isError ? presentProductError("connector_list", query.error) : null;
  const lifecycleError = actionError ? presentProductError("connector_lifecycle", actionError) : null;

  async function runLifecycle(action: () => Promise<unknown>): Promise<void> {
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(error);
    }
  }

  return (
    <section className="space-y-6" aria-labelledby="connector-dashboard-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id="connector-dashboard-heading" className="text-lg font-semibold text-slate-900">
            Connected mailboxes
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Each card is one mailbox account. Disconnect removes its active authorization. Reconnect
            same account restores that same mailbox. Connecting a different account is a separate
            operation.
          </p>
        </div>
        <Button
          className="w-full sm:w-auto"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
          aria-busy={query.isFetching && !query.isPending}
        >
          {REFRESH_LABEL}
        </Button>
      </div>

      {notice ? <OAuthReturnNotice tone={notice.tone} text={notice.text} /> : null}
      {lifecycleError ? (
        <ProductErrorState
          {...lifecycleError}
          onRetry={
            lifecycleError.retryLabel === REFRESH_LABEL ? () => void query.refetch() : undefined
          }
        />
      ) : null}

      {query.isPending ? <LoadingSkeleton /> : null}
      {listError ? (
        <ProductErrorState {...listError} onRetry={() => void query.refetch()} />
      ) : null}

      {query.isSuccess ? (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((account) => (
            <ConnectorCard
              key={account.id}
              account={account}
              connectBusy={connectBusy}
              onReconnect={(target) => {
                void runLifecycle(() => mutations.reauthorize.mutateAsync(target.id));
              }}
              onDisconnect={setPendingDisconnect}
            />
          ))}
          {!hasGmail ? (
            <MissingProviderCard
              provider="gmail"
              busy={connectBusy}
              canConnect={canConnect}
              onConnect={() => {
                void runLifecycle(() => mutations.gmailConnect.mutateAsync());
              }}
            />
          ) : null}
          {!hasGraph ? (
            <MissingProviderCard
              provider="microsoft_graph"
              busy={connectBusy}
              canConnect={canConnect}
              onConnect={() => {
                void runLifecycle(() => mutations.microsoftConnect.mutateAsync());
              }}
            />
          ) : null}
        </div>
      ) : null}

      {query.isSuccess && canConnect && (hasGmail || hasGraph) ? (
        <div className="flex flex-col gap-3">
          {hasGmail ? (
            <ConnectAnotherAccount
              provider="gmail"
              busy={connectBusy}
              onConnect={() => {
                void runLifecycle(() => mutations.gmailConnectAnother.mutateAsync());
              }}
            />
          ) : null}
          {hasGraph ? (
            <ConnectAnotherAccount
              provider="microsoft_graph"
              busy={connectBusy}
              onConnect={() => {
                void runLifecycle(() => mutations.microsoftConnectAnother.mutateAsync());
              }}
            />
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={pendingDisconnect !== null}
        title={pendingDisconnect ? `Disconnect ${providerLabel(pendingDisconnect.provider)}?` : "Disconnect mailbox?"}
        description="This removes ECI's active mailbox authorization for this mailbox account. Reconnect same account restores this same mailbox later."
        confirmLabel="Disconnect"
        onCancel={() => setPendingDisconnect(null)}
        onConfirm={() => {
          if (pendingDisconnect === null) {
            return;
          }
          const target = pendingDisconnect;
          setPendingDisconnect(null);
          void runLifecycle(() => mutations.disconnect.mutateAsync(target.id));
        }}
      />
    </section>
  );
}

function MissingProviderCard({
  provider,
  busy,
  canConnect,
  onConnect,
}: {
  provider: "gmail" | "microsoft_graph";
  busy: boolean;
  canConnect: boolean;
  onConnect: () => void;
}) {
  const label = providerLabel(provider);
  const actionLabel = provider === "gmail" ? "Connect Gmail" : "Connect Microsoft Outlook";
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-lg border border-dashed border-slate-300 bg-white p-5">
      <div className="min-w-0">
        <h3 className="text-base font-semibold break-words text-slate-900">{label}</h3>
        <p className="mt-1 text-sm text-slate-600">No mailbox is connected for this provider.</p>
      </div>
      <PermissionGate
        permission="communications:connect"
        fallback={
          <p className="text-sm text-slate-600">
            Connecting a mailbox requires the communications:connect permission.
          </p>
        }
      >
        <Button className="w-full sm:w-auto" onClick={onConnect} disabled={busy || !canConnect}>
          {actionLabel}
        </Button>
      </PermissionGate>
    </article>
  );
}
