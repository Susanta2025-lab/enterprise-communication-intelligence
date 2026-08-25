import { useEffect, useState } from "react";

import type { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import { EciApiError, messageForKind } from "../api/errors";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { ConfirmDialog } from "../components/connectors/ConfirmDialog";
import { ConnectorCard } from "../components/connectors/ConnectorCard";
import { ErrorState } from "../components/connectors/ErrorState";
import { LoadingSkeleton } from "../components/connectors/LoadingSkeleton";
import { OAuthReturnNotice } from "../components/connectors/OAuthReturnNotice";
import { PermissionGate } from "../components/connectors/PermissionGate";
import { providerLabel } from "../components/connectors/copy";
import { Button } from "../components/ui/button";
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
  const [actionError, setActionError] = useState<string | null>(null);

  const refetch = query.refetch;
  useEffect(() => {
    if (shouldRefresh) {
      void refetch();
    }
  }, [refetch, shouldRefresh]);

  const connectBusy =
    mutations.gmailConnect.isPending ||
    mutations.microsoftConnect.isPending ||
    mutations.reauthorize.isPending ||
    mutations.disconnect.isPending;

  const items = query.data?.items ?? [];
  const hasGmail = items.some((item) => item.provider === "gmail");
  const hasGraph = items.some((item) => item.provider === "microsoft_graph");
  const canConnect = hasPermission(permissions, "communications:connect");

  async function runLifecycle(action: () => Promise<unknown>): Promise<void> {
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(errorMessage(error, "Mailbox connection could not be started. Try again."));
    }
  }

  return (
    <section className="space-y-6" aria-labelledby="connector-dashboard-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="connector-dashboard-heading" className="text-lg font-semibold text-slate-900">
            Connected mailboxes
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Connect Gmail or Microsoft Outlook. Open an active mailbox to browse recent messages.
          </p>
        </div>
        <Button onClick={() => void query.refetch()} disabled={query.isFetching}>
          Refresh
        </Button>
      </div>

      {notice ? <OAuthReturnNotice tone={notice.tone} text={notice.text} /> : null}
      {actionError ? <ErrorState message={actionError} /> : null}

      {query.isPending ? <LoadingSkeleton /> : null}
      {query.isError ? (
        <ErrorState
          message={errorMessage(query.error, "Connector accounts could not be loaded.")}
          onRetry={() => void query.refetch()}
        />
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

      <ConfirmDialog
        open={pendingDisconnect !== null}
        title={pendingDisconnect ? `Disconnect ${providerLabel(pendingDisconnect.provider)}?` : "Disconnect mailbox?"}
        description="This removes ECI's active mailbox authorization for this connection. You can reconnect later."
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
    <article className="flex flex-col gap-4 rounded-lg border border-dashed border-slate-300 bg-white p-5">
      <div>
        <h3 className="text-base font-semibold text-slate-900">{label}</h3>
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
        <Button onClick={onConnect} disabled={busy || !canConnect}>
          {actionLabel}
        </Button>
      </PermissionGate>
    </article>
  );
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof EciApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message === "authorization_url_invalid") {
    return "Mailbox authorization could not be started safely.";
  }
  if (error instanceof Error && error.message) {
    return fallback;
  }
  return messageForKind("http_error");
}
