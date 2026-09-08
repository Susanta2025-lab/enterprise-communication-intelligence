import { useQuery } from "@tanstack/react-query";

import type { EciApiClient } from "../api/client";
import { isAiImageInputAvailable } from "../api/health";

export const PLATFORM_HEALTH_QUERY_KEY = ["platform-health"] as const;

export function usePlatformHealth(apiClient: EciApiClient, enabled: boolean) {
  return useQuery({
    queryKey: PLATFORM_HEALTH_QUERY_KEY,
    queryFn: () => apiClient.getPlatformHealth(),
    enabled,
    staleTime: 60_000,
  });
}

export function useImageAnalysisAvailable(apiClient: EciApiClient, enabled: boolean): boolean {
  const health = usePlatformHealth(apiClient, enabled);
  return isAiImageInputAvailable(health.data?.ai_image_input);
}
