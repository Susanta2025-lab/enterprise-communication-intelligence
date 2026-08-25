import type { EciApiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiStatusPanel } from "../components/ApiStatusPanel";
import { AppShell } from "../components/AppShell";
import { SignInPanel } from "../components/SignInPanel";

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
      <ApiStatusPanel apiClient={apiClient} enabled />
    </AppShell>
  );
}
