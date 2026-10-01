import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { EciApiClient } from "../../api/client";
import { useTrackingAccess } from "../../hooks/useWorkItems";
import { Button } from "../ui/button";
import { WorkError } from "./WorkError";

export function ContextPicker({ api, value, onChange, includeArchived = false, disabled = false, emptyLabel = "Unassociated" }: {
  api: EciApiClient;
  value: string;
  onChange: (value: string) => void;
  includeArchived?: boolean;
  disabled?: boolean;
  emptyLabel?: string;
}) {
  const { identity, allowed } = useTrackingAccess();
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["contexts", identity, "picker", includeArchived, offset],
    queryFn: () => api.listContexts({ limit: 20, offset, includeArchived }),
    enabled: allowed,
  });
  return <div className="space-y-2">
    <label>Business Context (optional)
      <select disabled={disabled} value={value} onChange={event => onChange(event.target.value)}>
        <option value="">{emptyLabel}</option>
        {value && !query.data?.items.some(context => context.id === value) &&
          <option value={value}>Keep selected context</option>}
        {query.data?.items.map(context =>
          <option key={context.id} value={context.id}>{context.title}{context.status === "archived" ? " (archived)" : ""}</option>)}
      </select>
    </label>
    <div className="flex flex-wrap gap-2">
      <Button type="button" disabled={disabled || !offset || query.isFetching} onClick={() => setOffset(n => n - 20)}>Previous contexts</Button>
      <Button type="button" disabled={disabled || query.isFetching || query.data?.items.length !== 20} onClick={() => setOffset(n => n + 20)}>Next contexts</Button>
    </div>
    {query.isPending && <p role="status">Loading contexts…</p>}
    <WorkError error={query.error} retry={() => void query.refetch()} />
  </div>;
}
