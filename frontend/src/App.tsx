import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

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
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
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
