import { ContextPicker } from "../components/workItems/ContextPicker";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { EciApiClient } from "../api/client";
import type { WorkQuery } from "../api/workItems";
import { useTrackingAccess, useWorkItems } from "../hooks/useWorkItems";
import { dueLabel } from "../lib/workItemDue";
import { WorkForm } from "../components/workItems/WorkForm";
import { WorkError } from "../components/workItems/WorkError";
import { Button } from "../components/ui/button";

export function WorkItemsListPage({ apiClient, contextId }: { apiClient: EciApiClient; contextId?: string }) {
  const { allowed, identity } = useTrackingAccess();
  return allowed ? <TrackingList key={`${identity}:${contextId ?? "global"}`} api={apiClient} contextId={contextId} /> : <p role="alert">Tracking requires communications:analyze permission.</p>;
}
function TrackingList({ api, contextId }: { api: EciApiClient; contextId?: string }) {
  const [query, setQuery] = useState<WorkQuery>({ limit: 20, offset: 0, business_context_id: contextId });
  const [creating, setCreating] = useState(false);
  const result = useWorkItems(api, query);
  const navigate = useNavigate();
  function filter(key: keyof WorkQuery, value: string | boolean | number | undefined) { setQuery(q => ({ ...q, [key]: value === "" ? undefined : value, offset: 0 })); }
  return <section className="space-y-4"><h2 className="text-lg font-semibold">Tracking</h2><p>Confirmed actions and obligations. Completion records a human declaration.</p>
    {!creating && <Button onClick={() => setCreating(true)}>Create Work Item</Button>}
    {creating && <WorkForm api={api} contextId={contextId} onCancel={() => setCreating(false)} onDone={id => navigate(`/tracking/${id}`)} />}
    <fieldset className="work-form grid gap-3 rounded border p-4 sm:grid-cols-3"><legend>Server-side filters</legend>
      <label>Kind filter<select value={query.kind ?? ""} onChange={e => filter("kind", e.target.value)}><option value="">All kinds</option><option value="action">Action</option><option value="obligation">Obligation</option></select></label>
      <label>Status<select value={query.status ?? ""} onChange={e => filter("status", e.target.value)}><option value="">All statuses</option>{["open","in_progress","completed","cancelled"].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Archive visibility<select value={query.archive ?? "active"} onChange={e => filter("archive", e.target.value)}>{["active","archived","all"].map(s => <option key={s}>{s}</option>)}</select></label>
      {!contextId && <><ContextPicker api={api} value={query.business_context_id ?? ""} disabled={query.unassociated} includeArchived emptyLabel="Any context" onChange={value => filter("business_context_id", value)} /><label><input type="checkbox" checked={query.unassociated ?? false} onChange={e => setQuery(q => ({ ...q, offset: 0, unassociated: e.target.checked, business_context_id: undefined }))} />Unassociated only</label></>}
      <label>Due kind<select value={query.due_kind ?? ""} onChange={e => setQuery(q => ({ ...q, offset: 0, due_kind: (e.target.value || undefined) as WorkQuery["due_kind"], due_date_from: undefined, due_date_to: undefined, due_at_from: undefined, due_at_to: undefined, sort: "created_desc" }))}><option value="">All deadlines</option><option value="none">No deadline</option><option value="date">Date-only</option><option value="datetime">Timed</option></select></label>
      {query.due_kind === "date" && <><label>Date from<input type="date" value={query.due_date_from ?? ""} onChange={e => filter("due_date_from", e.target.value)} /></label><label>Date through<input type="date" value={query.due_date_to ?? ""} onChange={e => filter("due_date_to", e.target.value)} /></label></>}
      {query.due_kind === "datetime" && <><label>Timed from (RFC 3339 with offset)<input placeholder="2026-09-27T09:00:00+01:00" value={query.due_at_from ?? ""} onChange={e => filter("due_at_from", e.target.value)} /></label><label>Timed through (RFC 3339 with offset)<input value={query.due_at_to ?? ""} onChange={e => filter("due_at_to", e.target.value)} /></label></>}
      <label>Overdue<select value={query.overdue === undefined ? "" : String(query.overdue)} onChange={e => filter("overdue", e.target.value === "" ? undefined : e.target.value === "true")}><option value="">Any</option><option value="true">Overdue</option><option value="false">Not overdue</option></select></label>
      <label>Sort<select value={query.sort ?? "created_desc"} onChange={e => filter("sort", e.target.value)}><option value="created_desc">Newest created</option>{(query.due_kind === "date" || query.due_kind === "datetime") && <option value="due_asc">Due ascending</option>}</select></label>
      <label>Page size<select value={query.limit} onChange={e => filter("limit", +e.target.value)}>{[20,50,100].map(n => <option key={n}>{n}</option>)}</select></label>
    </fieldset>
    {result.isPending && <p role="status">Loading tracking…</p>}<WorkError error={result.error} retry={() => void result.refetch()} />
    {result.data?.items.length === 0 && <p>No work items match these filters.</p>}
    <ul className="space-y-3">{result.data?.items.map(item => <li key={item.id} className="rounded border bg-white p-4"><Link className="font-semibold underline" to={`/tracking/${item.id}`}>{item.title}</Link><p>{item.kind} · {item.status} {item.archived_at ? "· Archived" : ""}</p><p>{dueLabel(item.due)} {item.overdue && <strong>Overdue</strong>}</p>{item.business_context_id && <Link className="underline" to={`/contexts/${item.business_context_id}`}>Business Context</Link>}<p>Created {item.created_at}</p></li>)}</ul>
    <div className="flex gap-3"><Button disabled={!query.offset || result.isFetching} onClick={() => setQuery(q => ({ ...q, offset: Math.max(0, (q.offset ?? 0) - (q.limit ?? 20)) }))}>Previous</Button><span>Page {Math.floor((query.offset ?? 0) / (query.limit ?? 20)) + 1}</span><Button disabled={result.isFetching || !result.data || result.data.items.length < (query.limit ?? 20)} onClick={() => setQuery(q => ({ ...q, offset: (q.offset ?? 0) + (q.limit ?? 20) }))}>Next</Button></div>
  </section>;
}
