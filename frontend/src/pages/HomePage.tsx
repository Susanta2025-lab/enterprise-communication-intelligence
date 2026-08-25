import type { EciApiClient } from "../api/client";
import { ApiStatusPanel } from "../components/ApiStatusPanel";
import { ConnectorDashboardPage } from "./ConnectorDashboardPage";

type HomePageProps = {
  apiClient: EciApiClient;
};

export function HomePage({ apiClient }: HomePageProps) {
  return (
    <div className="space-y-8">
      <ConnectorDashboardPage apiClient={apiClient} />
      <ApiStatusPanel apiClient={apiClient} enabled />
    </div>
  );
}
