import { useState } from "react";

import type { EciApiClient } from "../api/client";
import { EciApiError } from "../api/errors";

export type ApiStatus = "idle" | "checking" | "ok" | "error";

export function useProtectedApiStatus(apiClient: EciApiClient, enabled: boolean) {
  const [status, setStatus] = useState<ApiStatus>("idle");
  const [message, setMessage] = useState("Protected API has not been checked yet.");

  async function checkConnection(): Promise<void> {
    if (!enabled) {
      return;
    }
    setStatus("checking");
    setMessage("Checking protected API connectivity…");
    try {
      await apiClient.getAnalysesSmoke();
      setStatus("ok");
      setMessage("Protected API responded successfully.");
    } catch (error) {
      setStatus("error");
      if (error instanceof EciApiError) {
        setMessage(error.message);
        return;
      }
      setMessage("Protected API connectivity could not be verified.");
    }
  }

  return { status, message, checkConnection };
}
