import type { EciApiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiStatusPanel } from "../components/ApiStatusPanel";
import { AppShell } from "../components/AppShell";
import { SignInPanel } from "../components/SignInPanel";
import { ConnectorDashboardPage } from "./ConnectorDashboardPage";

type HomePageProps = {
  apiClient: EciApiClient;
};

export function HomePage({ apiClient }: HomePageProps) {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <SignInPanel />;
  }

  return (
    <AppShell>
      <div className="space-y-8">
        <ConnectorDashboardPage apiClient={apiClient} />
        <ApiStatusPanel apiClient={apiClient} enabled />
      </div>
    </AppShell>
  );
}
