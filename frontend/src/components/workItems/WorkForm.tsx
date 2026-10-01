import { ContextPicker } from "./ContextPicker";
import { CreationDraftContext } from "./creationDrafts";
import { useContext, useEffect, useRef, useState } from "react";
import type { EciApiClient } from "../../api/client";
import type { Candidate, Due, WorkCreate, WorkDetail, WorkFields } from "../../api/workItems";
import { calendarDate, editableWallTime, timedChoices, zoneFormatter } from "../../lib/workItemDue";
import { useInvalidateTracking, useWorkRequest } from "../../hooks/useWorkItems";
import { EciApiError } from "../../api/errors";
import { Button } from "../ui/button";
import { WorkError } from "./WorkError";

export function WorkForm({ api, item, candidate, contextId, onDone, onCancel }: { api: EciApiClient; item?: WorkDetail; candidate?: Candidate; contextId?: string; onDone: (id: string) => void; onCancel: () => void }) {
  const drafts = useContext(CreationDraftContext);
  const draftId = candidate ? JSON.stringify(candidate.candidate) : "manual";
  const recovery = item ? undefined : drafts?.get(draftId)?.body;
  const [title, setTitle] = useState(recovery?.title ?? item?.title ?? "");
  const [description, setDescription] = useState(recovery?.description ?? item?.description ?? "");
  const [kind, setKind] = useState<WorkCreate["kind"] | "">(recovery?.kind ?? item?.kind ?? "");
  const [context, setContext] = useState(recovery ? recovery.business_context_id ?? "" : item?.business_context_id ?? contextId ?? "");
  const [mode, setMode] = useState<Due["kind"] | "">(recovery?.due.kind ?? item?.due.kind ?? "");
  const initialDue = recovery?.due ?? item?.due;
  const [zone, setZone] = useState(initialDue && initialDue.kind !== "none" ? initialDue.timezone : Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [confirmedZone, setConfirmedZone] = useState(false);
  const [date, setDate] = useState(initialDue?.kind === "date" ? initialDue.date : "");
  const [local, setLocal] = useState(() => editableWallTime(initialDue));
  const [choice, setChoice] = useState("");
  const [choices, setChoices] = useState<string[] | null>(null);
  const [validation, setValidation] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [key] = useState(() => recovery?.creation_key ?? crypto.randomUUID());
  const [submitted, setSubmitted] = useState<WorkCreate | null>(recovery ?? null);
  const titleRef = useRef<HTMLInputElement>(null);
  const request = useWorkRequest();
  const invalidate = useInvalidateTracking();
  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    titleRef.current?.focus();
    return () => { if (trigger?.isConnected) trigger.focus(); };
  }, []);
  const frozen = !item && submitted !== null;
  async function submit() {
    setValidation(""); setError(null);
    let body = submitted;
    if (!body || item) {
      try {
        if (!title.trim() || title.trim().length > 200 || !kind || !mode) throw new Error("Choose a kind, a due mode and a meaningful title of 1–200 characters.");
        let due: Due = { kind: "none" };
        if (mode !== "none") {
          zoneFormatter(zone);
          if (!confirmedZone) throw new Error("Confirm the business timezone explicitly.");
          if (mode === "date") due = { kind: "date", date: calendarDate(date), timezone: zone };
          else {
            const valid = timedChoices(local, zone);
            if (!valid.length) throw new Error("This local time does not exist in the selected timezone. Choose another time.");
            if (valid.length > 1 && !valid.includes(choice)) { setChoices(valid); throw new Error("This local time repeats. Choose the intended offset."); }
            due = { kind: "datetime", at: valid.length === 1 ? valid[0] : choice, timezone: zone };
          }
        }
        body = { creation_key: key, kind, title: title.trim(), description: description.trim() || null, due, business_context_id: context || null };
      } catch (e) { setValidation((e as Error).message); return; }
    }
    if (!item) { setSubmitted(body); drafts?.set(draftId, { body, candidate }); }
    setBusy(true);
    try {
      const fields: WorkFields = { title: body.title, description: body.description, due: body.due, business_context_id: body.business_context_id };
      const result = await request(signal => item ? api.editWorkItem(item.id, { ...fields, expected_version: item.version }, signal) : api.createWorkItem(candidate ? { ...body, candidate: candidate.candidate, confirmed: true } : body, signal));
      if (!item) drafts?.delete(draftId);
      void invalidate(); onDone(result.id);
    } catch (e) { if (!(e instanceof DOMException && e.name === "AbortError")) {
      setError(e);
      if (e instanceof EciApiError && ([400, 401, 403, 404, 422].includes(e.status) || e.code === "work_item_context_archived" || e.code === "work_item_candidate_changed")) { setSubmitted(null); drafts?.delete(draftId); }
    } }
    finally { setBusy(false); }
  }
  return <form className="work-form space-y-4 rounded border bg-white p-4" onSubmit={e => { e.preventDefault(); void submit(); }}>
    {candidate && <section aria-label="Original AI observation" className="break-words"><h3>AI suggestion — review required</h3><p>Source: {candidate.candidate.source_kind}; {candidate.candidate.field}. Dates and actions are independent observations.</p><pre className="whitespace-pre-wrap font-sans">{typeof candidate.value === "string" ? candidate.value : JSON.stringify(candidate.value, null, 2)}</pre>{candidate.truncated && <p>Source analysis was truncated.</p>}{[...candidate.warnings, ...candidate.limitations].map((w,i) => <p key={i}>{w}</p>)}</section>}
    {initialDue?.kind === "datetime" && !editableWallTime(initialDue) && <p role="alert">The saved timezone is unavailable in this browser. The server value remains authoritative. To change the deadline, explicitly review a supported timezone and local time.</p>}
    {frozen && <p role="status">The submitted fields are retained for safe retry. Retry to recover the original result before starting a different item. Closing this form keeps recovery state in this signed-in session. Reopening resumes the original request; signing out or refreshing clears it. After a refresh, inspect Tracking for the saved item before submitting a new creation.</p>}
    <fieldset disabled={busy || frozen} className="grid gap-4 sm:grid-cols-2">
      <label>Kind<select required value={kind} disabled={!!item} onChange={e => setKind(e.target.value as typeof kind)}><option value="">Choose kind</option><option value="action">Action</option><option value="obligation">Obligation</option></select></label>
      <label>Reviewed title<input ref={titleRef} required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label>Description<textarea maxLength={4000} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <ContextPicker api={api} value={context} onChange={setContext} />
      <label>Due mode<select required value={mode} onChange={e => { setMode(e.target.value as typeof mode); setChoice(""); setChoices(null); }}><option value="">Review deadline</option><option value="none">No deadline</option><option value="date">Date-only deadline</option><option value="datetime">Timed deadline</option></select></label>
      {mode === "date" && <label>Calendar date<input type="date" required value={date} onChange={e => setDate(e.target.value)} /></label>}
      {mode === "datetime" && <label>Local date and time<input type="datetime-local" step="1" required value={local} onChange={e => { setLocal(e.target.value); setChoice(""); setChoices(null); }} /></label>}
      {mode && mode !== "none" && <><label>IANA timezone<input required value={zone} onChange={e => { setZone(e.target.value); setConfirmedZone(false); setChoice(""); setChoices(null); }} /></label><label><input type="checkbox" checked={confirmedZone} onChange={e => setConfirmedZone(e.target.checked)} />I confirm this business timezone (browser suggestion is editable)</label></>}
      {choices && <label>Repeated-time offset<select required value={choice} onChange={e => setChoice(e.target.value)}><option value="">Choose offset</option>{choices.map(c => <option key={c} value={c}>{c.slice(-6)}</option>)}</select></label>}
    </fieldset>
    {validation && <p role="alert">{validation}</p>}<WorkError error={error} retry={item ? () => { void invalidate(); onCancel(); } : undefined} />
    <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy}>{busy ? "Saving…" : frozen ? "Retry original creation" : item ? "Save reviewed changes" : candidate ? "Confirm and create tracked item" : "Create Work Item"}</Button><Button type="button" disabled={busy} onClick={onCancel}>Cancel</Button></div>
  </form>;
}
