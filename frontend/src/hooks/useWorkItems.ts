import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { EciApiClient } from "../api/client";
import type { WorkQuery } from "../api/workItems";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";

export const workKeys = { root: ["work-items"] as const, owner: (identity: string | null) => ["work-items", identity] as const };
export function useTrackingAccess() {
  const auth = useAuth();
  return { identity: auth.accountKey, allowed: auth.isAuthenticated && hasPermission(auth.permissions, "communications:analyze") };
}
export function useWorkItems(api: EciApiClient, query: WorkQuery) {
  const { identity, allowed } = useTrackingAccess();
  return useQuery({ queryKey: [...workKeys.owner(identity), "list", query], queryFn: ({ signal }) => api.listWorkItems(query, signal), enabled: allowed });
}
/** Abort writes on unmount/identity change and guard callbacks after completion. */
export function useWorkRequest() {
  const { identity } = useTrackingAccess();
  const current = useRef(identity);
  current.current = identity;
  const pending = useRef(new Set<AbortController>());
  useEffect(() => { const requests = pending.current; return () => { requests.forEach(c => c.abort()); requests.clear(); }; }, [identity]);
  return async <T,>(request: (signal: AbortSignal) => Promise<T>): Promise<T> => {
    const started = identity;
    const controller = new AbortController();
    pending.current.add(controller);
    try {
      const value = await request(controller.signal);
      if (current.current !== started || controller.signal.aborted) throw new DOMException("Identity changed", "AbortError");
      return value;
    } finally { pending.current.delete(controller); }
  };
}
export function useInvalidateTracking() {
  const client = useQueryClient();
  return async () => {
    // Includes both previous and next context, and every current-association list.
    await Promise.all([client.invalidateQueries({ queryKey: workKeys.root }), client.invalidateQueries({ queryKey: ["contexts"] })]);
  };
}
