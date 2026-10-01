import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { EciApiClient } from "../api/client";
import type { WorkDetail, WorkEvent, WorkStatus } from "../api/workItems";
import { useInvalidateTracking, useTrackingAccess, useWorkRequest, workKeys } from "../hooks/useWorkItems";
import { dueLabel } from "../lib/workItemDue";
import { WorkForm } from "../components/workItems/WorkForm";
import { WorkError } from "../components/workItems/WorkError";
import { ConfirmDialog } from "../components/connectors/ConfirmDialog";
import { Button } from "../components/ui/button";
export function WorkItemDetailPage({ apiClient }: { apiClient: EciApiClient }) {
  const { itemId = "" } = useParams();
  const { allowed, identity } = useTrackingAccess();
  return allowed ? <Detail key={`${identity}:${itemId}`} api={apiClient} id={itemId} /> : <p role="alert">Tracking requires communications:analyze permission.</p>;
}
function Detail({ api, id }: { api: EciApiClient; id: string }) {
  const { identity } = useTrackingAccess();
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<WorkDetail | null>(null);
  const [pending, setPending] = useState<{ action: string; version: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const request = useWorkRequest(); const invalidate = useInvalidateTracking();
  const query = useQuery({ queryKey: [...workKeys.owner(identity), id], queryFn: ({ signal }) => api.getWorkItem(id, signal) });
  const events = useQuery({ queryKey: [...workKeys.owner(identity), id, "events", offset], queryFn: ({ signal }) => api.workItemEvents(id, offset, signal), enabled: !!query.data });
  const item = query.data;
  async function transition() {
    if (!item || !pending) return;
    setBusy(true); setError(null);
    try {
      const operation = pending.action === "archive" || pending.action === "restore" ? pending.action : "status";
      await request(signal => api.transitionWorkItem(id, operation, { expected_version: pending.version, ...(operation === "status" ? { status: (pending.action === "reopen" ? "open" : pending.action) as WorkStatus, reopen: pending.action === "reopen" } : {}) }, signal));
      await invalidate();
    } catch (e) { if (!(e instanceof DOMException && e.name === "AbortError")) setError(e); }
    finally { setBusy(false); setPending(null); }
  }
  const terminal = item?.status === "completed" || item?.status === "cancelled";
  return <section className="space-y-4"><Link to="/tracking">Tracking</Link>{query.isPending && <p role="status">Loading work item…</p>}<WorkError error={query.error || error} retry={() => { setEditing(null); setError(null); void query.refetch(); }} />
    {item && <><h2 className="text-lg font-semibold">{item.title}</h2><p>{item.kind} · {item.status} · {item.archived_at ? "Archived" : "Unarchived"}</p><p>{item.description}</p><p>{dueLabel(item.due)} {item.overdue && <strong>Overdue</strong>}</p><p>Origin: {item.creation_origin === "manual" ? "Manual" : "AI suggestion confirmed by user"}</p>{item.confirmed_at && <p>Confirmed {item.confirmed_at}</p>}<p>Created {item.created_at} · Updated {item.updated_at} · Version {item.version}</p>{item.business_context_id && <Link className="underline" to={`/contexts/${item.business_context_id}`}>Business Context</Link>}
      {terminal && <p>Completion/cancellation is human-marked. Reopen before editing business fields.</p>}
      <div className="flex flex-wrap gap-3">{!item.archived_at && !terminal && <Button onClick={() => setEditing(item)}>Edit work item</Button>}{(item.archived_at ? ["restore"] : terminal ? ["reopen", "archive"] : ["open", "in_progress", "completed", "cancelled", "archive"]).filter(a => a !== item.status).map(action => <Button key={action} onClick={() => setPending({ action, version: item.version })}>{({ open: "Open", in_progress: "In progress", completed: "Complete", cancelled: "Cancel item", reopen: "Reopen", archive: "Archive", restore: "Restore" } as Record<string,string>)[action]}</Button>)}</div>
      {editing && !terminal && !item.archived_at && <WorkForm api={api} item={editing} onCancel={() => setEditing(null)} onDone={() => setEditing(null)} />}
      <section><h3>Sources</h3><p>Availability reflects saved metadata; live provider content has not been verified. Unavailable sources do not invalidate this item.</p>{!item.sources.length && <p>No sources (manual tracking).</p>}<ul>{item.sources.map((source,i) => <li key={i}>{source.source_kind}: {source.availability} {source.candidate_field && `· ${source.candidate_field} observation ${source.candidate_index}`}<dl className="break-all">{source.analysis_id && <><dt>Analysis reference</dt><dd>{source.analysis_id}</dd></>}{source.attachment_analysis_id && <><dt>Attachment analysis reference</dt><dd>{source.attachment_analysis_id}</dd></>}{source.connector_account_id && <><dt>Mailbox connection reference</dt><dd>{source.connector_account_id}</dd></>}{source.provider_message_id && <><dt>Source message reference</dt><dd>{source.provider_message_id}</dd></>}{source.provider_attachment_id && <><dt>Source attachment reference</dt><dd>{source.provider_attachment_id}</dd></>}</dl></li>)}</ul></section>
      <section><h3>Event history</h3>{events.isPending && <p role="status">Loading history…</p>}<WorkError error={events.error} retry={() => void events.refetch()} /><ol>{events.data?.items.map(e => <li key={e.id}>{eventDescription(e)} · <time>{e.occurred_at}</time> · Version {e.item_version}{e.context_at_event_id && <Link to={`/contexts/${e.context_at_event_id}`}> · Recorded context</Link>}</li>)}</ol><Button disabled={!offset} onClick={() => setOffset(n => n - 20)}>Earlier page</Button><Button disabled={events.data?.items.length !== 20} onClick={() => setOffset(n => n + 20)}>Later page</Button></section>
    </>}
    <ConfirmDialog open={pending !== null} title="Confirm tracking change" description={`Apply ${pending?.action.replaceAll("_", " ") ?? "change"}? This records your declaration; it does not independently verify fulfillment.`} confirmLabel="Confirm change" confirmBusy={busy} onCancel={() => { if (!busy) setPending(null); }} onConfirm={() => void transition()} />
  </section>;
}

function eventDescription(event: WorkEvent): string {
  const metadata = event.metadata;
  if (event.event_type === "status_changed") return `Human-marked status: ${metadata.old_status} → ${metadata.new_status}`;
  if (event.event_type === "edited") {
    const dueChange = metadata.old_due && metadata.new_due ? `; ${dueLabel(metadata.old_due)} → ${dueLabel(metadata.new_due)}` : "";
    return `Edited ${metadata.changed_fields?.join(", ") ?? "business fields"}${dueChange}`;
  }
  return `Work item ${event.event_type.replaceAll("_", " ")}`;
}
