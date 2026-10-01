import { CreationDraftContext } from "./creationDrafts";
import { useContext, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { EciApiClient } from "../../api/client";
import type { Candidate, CandidateQuery } from "../../api/workItems";
import { useTrackingAccess, workKeys } from "../../hooks/useWorkItems";
import { WorkForm } from "./WorkForm";
import { WorkError } from "./WorkError";
import { Button } from "../ui/button";
export function CandidatePanel({ api, source }: { api: EciApiClient; source: CandidateQuery }) {
  const { allowed, identity } = useTrackingAccess();
  return allowed ? <Candidates key={`${identity}:${source.source_kind}:${source.source_id}`} api={api} source={source} /> : null;
}
function Candidates({ api, source }: { api: EciApiClient; source: CandidateQuery }) {
  const drafts = useContext(CreationDraftContext);
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const { identity } = useTrackingAccess();
  const navigate = useNavigate();
  const query = useQuery({ queryKey: [...workKeys.owner(identity), "candidates", source, offset], queryFn: ({ signal }) => api.workCandidates({ ...source, limit: 20, offset }, signal), enabled: open });
  return <section className="space-y-3"><Button onClick={() => { setOpen(v => !v);
      const recovery = !open ? [...(drafts?.values() ?? [])].find(draft => draft.candidate?.candidate.source_id === source.source_id && draft.candidate?.candidate.source_kind === source.source_kind) : undefined;
      setSelected(recovery?.candidate ?? null); }}>{open ? "Close tracking candidates" : "Review tracking candidates"}</Button>
    {open && <><p>Persisted AI observations are advisory. Selecting one creates nothing. Actions and dates are independent; amounts are not tracking candidates.</p>{query.isPending && <p role="status">Loading candidates…</p>}<WorkError error={query.error} retry={() => void query.refetch()} />{query.data?.items.length === 0 && <p>No tracking candidates.</p>}
    {!selected && <><ul className="space-y-3">{query.data?.items.map(candidate => <li key={`${candidate.candidate.field}:${candidate.candidate.index}`} className="break-words rounded border p-3"><p>{candidate.candidate.field}</p><pre className="whitespace-pre-wrap font-sans">{typeof candidate.value === "string" ? candidate.value : JSON.stringify(candidate.value, null, 2)}</pre>{candidate.truncated && <p>Source analysis was truncated.</p>}{[...candidate.warnings, ...candidate.limitations].map((w,i) => <p key={i}>{w}</p>)}<Button onClick={() => setSelected(candidate)}>Create tracked item</Button></li>)}</ul><Button disabled={!offset} onClick={() => setOffset(n => n - 20)}>Previous candidates</Button><Button disabled={query.data?.items.length !== 20} onClick={() => setOffset(n => n + 20)}>Next candidates</Button></>}
    {selected && <WorkForm api={api} candidate={selected} onCancel={() => setSelected(null)} onDone={id => navigate(`/tracking/${id}`)} />}</>}
  </section>;
}
