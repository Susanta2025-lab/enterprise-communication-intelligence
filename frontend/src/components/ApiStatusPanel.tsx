import { useProtectedApiStatus } from "../hooks/useProtectedApiStatus";
import type { EciApiClient } from "../api/client";
import { Button } from "./ui/button";

type ApiStatusPanelProps = {
  apiClient: EciApiClient;
  enabled: boolean;
};

export function ApiStatusPanel({ apiClient, enabled }: ApiStatusPanelProps) {
  const { status, message, checkConnection } = useProtectedApiStatus(apiClient, enabled);

  return (
    <section className="min-w-0 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold">Protected API status</h2>
      <p className="mt-1 text-sm text-slate-600">
        Uses <code className="rounded bg-slate-100 px-1">GET /api/v1/analyses?limit=1</code> as
        the authenticated smoke contract.
      </p>
      <div className="mt-4">
        <Button
          className="w-full sm:w-auto"
          onClick={() => void checkConnection()}
          disabled={!enabled || status === "checking"}
        >
          Check API connection
        </Button>
      </div>
      <p
        className="mt-3 text-sm text-slate-700"
        data-testid="api-status-message"
        data-status={status}
        role={status === "error" ? "alert" : "status"}
        aria-live="polite"
      >
        {message}
      </p>
    </section>
  );
}
