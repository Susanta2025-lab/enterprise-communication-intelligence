import { CreationDraftContext, type CreationDrafts } from "./components/workItems/creationDrafts";
import { QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes, useParams } from "react-router-dom";

import type { EciApiClient } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import { CurrentUserProvider } from "./auth/CurrentUserContext";
import { AppShell } from "./components/AppShell";
import { AppErrorBoundary } from "./components/feedback/AppErrorBoundary";
import { SignInPanel } from "./components/SignInPanel";
import type { FrontendConfig } from "./config/env";
import { ContextsListPage } from "./pages/ContextsListPage";
import { HomePage } from "./pages/HomePage";
import { createQueryClient } from "./query/queryClient";

const WorkItemsListPage = lazy(() => import("./pages/WorkItemsListPage").then(module => ({ default: module.WorkItemsListPage })));

const WorkItemDetailPage = lazy(() => import("./pages/WorkItemDetailPage").then(module => ({ default: module.WorkItemDetailPage })));

const ContextWorkspacePage = lazy(() => import("./pages/ContextWorkspacePage").then(module => ({ default: module.ContextWorkspacePage })));

const MailboxWorkspacePage = lazy(() => import("./pages/MailboxWorkspacePage").then(module => ({ default: module.MailboxWorkspacePage })));

type AppProps = {
  apiClient: EciApiClient;
  config: FrontendConfig;
};

export function App(props: AppProps) {
  const { accountKey, isAuthenticated } = useAuth();
  return <IdentityApp key={`${isAuthenticated}:${accountKey ?? ""}`} {...props} />;
}

function IdentityApp({ apiClient, config }: AppProps) {
  const [queryClient] = useState(() => createQueryClient());
  const [creationDrafts] = useState<CreationDrafts>(() => new Map());

  useEffect(() => () => {
    void queryClient.cancelQueries();
    queryClient.clear();
    creationDrafts.clear();
  }, [queryClient, creationDrafts]);

  return (
    <CreationDraftContext.Provider value={creationDrafts}>
    <QueryClientProvider client={queryClient}>
      <AppErrorBoundary>
        <BrowserRouter>
          <AppRoutes apiClient={apiClient} config={config} />
        </BrowserRouter>
      </AppErrorBoundary>
    </QueryClientProvider>
    </CreationDraftContext.Provider>
  );
}

function ContextWorkspaceRoute({ apiClient }: { apiClient: EciApiClient }) {
  const { contextId } = useParams<{ contextId: string }>();
  if (!contextId) {
    return null;
  }
  return <ContextWorkspacePage apiClient={apiClient} contextId={contextId} />;
}

function AppRoutes({ apiClient, config }: AppProps) {
  const { isAuthenticated, interactionInProgress, accountKey } = useAuth();
  const queryClient = useQueryClient();

  useEffect(() => {
    return () => {
      for (const key of ["work-items", "contexts", "attachment-analyses", "mailbox-attachments"]) {
        void queryClient.cancelQueries({ queryKey: [key] });
        queryClient.removeQueries({ queryKey: [key] });
      }
    };
  }, [accountKey, queryClient]);

  useEffect(() => {
    if (!isAuthenticated) {
      queryClient.removeQueries({ queryKey: ["mailbox-attachments"] });
      queryClient.removeQueries({ queryKey: ["attachment-analyses"] });
      queryClient.removeQueries({ queryKey: ["contexts"] });
    }
  }, [isAuthenticated, queryClient]);

  if (!isAuthenticated) {
    // MsalProvider owns redirect completion; avoid Sign-in until Startup/redirect ends.
    if (interactionInProgress) {
      return (
        <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-16 sm:px-6">
          <p className="text-sm text-slate-600" role="status">
            Completing sign-in…
          </p>
        </main>
      );
    }
    return <SignInPanel />;
  }

  return (
    <CurrentUserProvider key={accountKey} apiClient={apiClient}>
      <AppShell
        deployment={{
          cloudProvider: config.cloudProvider,
          aiProvider: config.aiProvider,
          cloudRegion: config.cloudRegion,
        }}
      >
        <Suspense fallback={<p role="status">Loading workspace…</p>}>
        <Routes>
          <Route path="/tracking" element={<WorkItemsListPage apiClient={apiClient} />} />
          <Route path="/tracking/:itemId" element={<WorkItemDetailPage apiClient={apiClient} />} />
          <Route path="/" element={<HomePage apiClient={apiClient} />} />
          <Route path="/contexts" element={<ContextsListPage apiClient={apiClient} />} />
          <Route
            path="/contexts/:contextId"
            element={<ContextWorkspaceRoute apiClient={apiClient} />}
          />
          <Route
            path="/mailbox/:connectorAccountId"
            element={<MailboxWorkspacePage apiClient={apiClient} />}
          />
        </Routes>
        </Suspense>
      </AppShell>
    </CurrentUserProvider>
  );
}
