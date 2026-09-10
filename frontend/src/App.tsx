import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type { EciApiClient } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { AppErrorBoundary } from "./components/feedback/AppErrorBoundary";
import { SignInPanel } from "./components/SignInPanel";
import { HomePage } from "./pages/HomePage";
import { MailboxWorkspacePage } from "./pages/MailboxWorkspacePage";
import { createQueryClient } from "./query/queryClient";

type AppProps = {
  apiClient: EciApiClient;
};

export function App({ apiClient }: AppProps) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <AppErrorBoundary>
        <BrowserRouter>
          <AppRoutes apiClient={apiClient} />
        </BrowserRouter>
      </AppErrorBoundary>
    </QueryClientProvider>
  );
}

function AppRoutes({ apiClient }: AppProps) {
  const { isAuthenticated, interactionInProgress } = useAuth();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isAuthenticated) {
      queryClient.removeQueries({ queryKey: ["mailbox-attachments"] });
      queryClient.removeQueries({ queryKey: ["attachment-analyses"] });
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
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage apiClient={apiClient} />} />
        <Route
          path="/mailbox/:connectorAccountId"
          element={<MailboxWorkspacePage apiClient={apiClient} />}
        />
      </Routes>
    </AppShell>
  );
}
