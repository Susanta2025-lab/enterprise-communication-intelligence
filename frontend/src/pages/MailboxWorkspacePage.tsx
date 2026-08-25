import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import type { MailboxMessageListItem } from "../api/mailbox";
import { EciApiError } from "../api/errors";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { MailboxEmptyState } from "../components/mailbox/MailboxEmptyState";
import { MailboxErrorState } from "../components/mailbox/MailboxErrorState";
import { MailboxHeader } from "../components/mailbox/MailboxHeader";
import { MailboxLoadingSkeleton } from "../components/mailbox/MailboxLoadingSkeleton";
import { MailboxUnavailableState } from "../components/mailbox/MailboxUnavailableState";
import { LoadMoreButton } from "../components/mailbox/LoadMoreButton";
import { MessageAnalysisSection } from "../components/mailbox/MessageAnalysisSection";
import { MessageList } from "../components/mailbox/MessageList";
import { SelectedMessagePanel } from "../components/mailbox/SelectedMessagePanel";
import { mailboxListErrorMessage, mailboxRetryLabel } from "../components/mailbox/copy";
import { LoadingSkeleton } from "../components/connectors/LoadingSkeleton";
import { ErrorState } from "../components/connectors/ErrorState";
import { providerLabel } from "../components/connectors/copy";
import { CONNECTOR_ACCOUNT_QUERY_KEY, useConnectorAccounts } from "../hooks/useConnectorAccounts";
import { useAnalyzeMailboxMessage } from "../hooks/useAnalyzeMailboxMessage";
import {
  flattenMailboxItems,
  refreshMailboxMessages,
  useMailboxMessages,
} from "../hooks/useMailboxMessages";

type MailboxWorkspacePageProps = {
  apiClient: EciApiClient;
};

export function MailboxWorkspacePage({ apiClient }: MailboxWorkspacePageProps) {
  const { connectorAccountId } = useParams<{ connectorAccountId: string }>();
  const { permissions } = useAuth();
  const queryClient = useQueryClient();
  const canRead = hasPermission(permissions, "communications:read");
  const canAnalyze = hasPermission(permissions, "communications:analyze");
  const connectorsQuery = useConnectorAccounts(apiClient, Boolean(connectorAccountId) && canRead);
  const account = connectorsQuery.data?.items.find((item) => item.id === connectorAccountId);
  const mailboxEnabled = Boolean(connectorAccountId) && canRead && account?.status === "active";
  const mailboxQuery = useMailboxMessages(apiClient, connectorAccountId ?? "", mailboxEnabled);
  const [selected, setSelected] = useState<MailboxMessageListItem | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const analysis = useAnalyzeMailboxMessage(
    apiClient,
    connectorAccountId ?? "",
    selected?.provider_message_id ?? null,
  );

  const items = useMemo(
    () => flattenMailboxItems(mailboxQuery.data?.pages),
    [mailboxQuery.data?.pages],
  );

  useEffect(() => {
    if (selected === null) {
      return;
    }
    if (!items.some((item) => item.provider_message_id === selected.provider_message_id)) {
      setSelected(null);
    }
  }, [items, selected]);

  const mailboxError = mailboxQuery.error;
  useEffect(() => {
    if (mailboxError instanceof EciApiError && mailboxError.status === 409) {
      void queryClient.invalidateQueries({ queryKey: CONNECTOR_ACCOUNT_QUERY_KEY });
    }
  }, [mailboxError, queryClient]);

  useEffect(() => {
    if (mailboxQuery.isError) {
      errorRef.current?.focus();
    }
  }, [mailboxQuery.isError, mailboxQuery.error]);

  const title = account ? `${providerLabel(account.provider)} mailbox` : "Mailbox";
  const listBusy = mailboxQuery.isFetching && !mailboxQuery.isPending;

  async function handleRefresh(): Promise<void> {
    if (!connectorAccountId) {
      return;
    }
    analysis.resetAnalysis();
    await refreshMailboxMessages(queryClient, connectorAccountId);
  }

  function handleAnalyze(): void {
    if (!selected || !canAnalyze) {
      return;
    }
    analysis.analyze(selected.provider_message_id);
  }

  function handleAnalysisRetry(): void {
    if (analysis.error instanceof EciApiError && analysis.error.status === 404) {
      void handleRefresh();
      return;
    }
    handleAnalyze();
  }

  function handleMailboxRecovery(): void {
    if (mailboxError instanceof EciApiError && mailboxError.status === 400) {
      void handleRefresh();
      return;
    }
    if (mailboxQuery.isFetchNextPageError) {
      void mailboxQuery.fetchNextPage();
      return;
    }
    void mailboxQuery.refetch();
  }

  if (!connectorAccountId) {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title="Mailbox" />
        <MailboxErrorState message="That mailbox connection is unavailable." />
      </section>
    );
  }

  if (!canRead) {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title="Mailbox" />
        <MailboxErrorState message="Viewing this mailbox requires the communications:read permission." />
      </section>
    );
  }

  if (connectorsQuery.isPending) {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title="Mailbox" />
        <LoadingSkeleton />
      </section>
    );
  }

  if (connectorsQuery.isError) {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title="Mailbox" />
        <ErrorState
          message="Connector accounts could not be loaded."
          onRetry={() => void connectorsQuery.refetch()}
        />
      </section>
    );
  }

  if (!account) {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title="Mailbox" />
        <MailboxErrorState message="That mailbox connection is unavailable." />
      </section>
    );
  }

  if (account.status === "reauth_required") {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title={title} />
        <MailboxUnavailableState
          title="Reauthorization required"
          message="This mailbox needs to be reconnected before messages can be loaded. Reconnect from the dashboard."
        />
      </section>
    );
  }

  if (account.status !== "active") {
    return (
      <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
        <MailboxHeader title={title} />
        <MailboxUnavailableState
          title="Mailbox disconnected"
          message="This mailbox is disconnected. Connect it from the dashboard to browse messages."
        />
      </section>
    );
  }

  const retryLabel = mailboxRetryLabel(mailboxQuery.error);
  const showList = items.length > 0;
  const showEmpty = mailboxQuery.isSuccess && items.length === 0 && !mailboxQuery.isFetchingNextPage;

  return (
    <section className="space-y-6" aria-labelledby="mailbox-workspace-heading">
      <MailboxHeader
        title={title}
        onRefresh={
          mailboxQuery.isSuccess || showList ? () => void handleRefresh() : undefined
        }
        refreshDisabled={mailboxQuery.isFetching}
        refreshing={listBusy && !mailboxQuery.isFetchingNextPage}
      />

      {mailboxQuery.isPending ? <MailboxLoadingSkeleton /> : null}

      {mailboxQuery.isError ? (
        <MailboxErrorState
          ref={errorRef}
          message={mailboxListErrorMessage(mailboxQuery.error)}
          onRetry={retryLabel ? () => handleMailboxRecovery() : undefined}
          retryLabel={retryLabel ?? undefined}
        />
      ) : null}

      {mailboxQuery.isSuccess || showList ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(16rem,24rem)_minmax(0,1fr)]">
          <div className={selected ? "hidden min-w-0 lg:block" : "block min-w-0"}>
            {showEmpty ? <MailboxEmptyState /> : null}
            {showList ? (
              <>
                {listBusy && !mailboxQuery.isFetchingNextPage ? (
                  <p role="status" className="mb-3 text-sm text-slate-600">
                    Refreshing mailbox
                  </p>
                ) : null}
                <MessageList
                  items={items}
                  selectedId={selected?.provider_message_id ?? null}
                  onSelect={setSelected}
                  busy={mailboxQuery.isFetching}
                />
                {mailboxQuery.hasNextPage ? (
                  <div className="mt-4">
                    <LoadMoreButton
                      onClick={() => void mailboxQuery.fetchNextPage()}
                      busy={mailboxQuery.isFetchingNextPage}
                    />
                  </div>
                ) : null}
                {mailboxQuery.isFetchingNextPage ? (
                  <p role="status" className="mt-2 text-sm text-slate-600">
                    Loading more messages
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
          <div className={selected ? "block min-w-0" : "hidden min-w-0 lg:block"}>
            <SelectedMessagePanel
              item={selected}
              provider={account.provider}
              onBackToList={() => setSelected(null)}
            >
              {selected ? (
                <MessageAnalysisSection
                  canAnalyze={canAnalyze}
                  pending={analysis.isPending}
                  result={analysis.result}
                  error={analysis.error}
                  onAnalyze={handleAnalyze}
                  onRetry={handleAnalysisRetry}
                />
              ) : null}
            </SelectedMessagePanel>
          </div>
        </div>
      ) : null}
    </section>
  );
}
