import { APPROVED_REPLY_HEADING, APPROVED_SNAPSHOT_BOUNDARY, PROPOSED_REPLY_HEADING, WORKFLOW_SNAPSHOT_BOUNDARY } from "./copy";

type WorkflowSnapshotProps = {
  body: string;
  variant: "proposed" | "approved";
};

export function WorkflowSnapshot({ body, variant }: WorkflowSnapshotProps) {
  const headingId = variant === "approved" ? "approved-reply-heading" : "proposed-reply-heading";
  const heading = variant === "approved" ? APPROVED_REPLY_HEADING : PROPOSED_REPLY_HEADING;
  const boundary = variant === "approved" ? APPROVED_SNAPSHOT_BOUNDARY : WORKFLOW_SNAPSHOT_BOUNDARY;

  return (
    <section aria-labelledby={headingId}>
      <h4 id={headingId} className="text-sm font-semibold text-slate-900">
        {heading}
      </h4>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">{boundary}</p>
      <pre className="mt-3 max-w-full overflow-x-hidden whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-white p-3 font-sans text-sm text-slate-800">
        {body}
      </pre>
    </section>
  );
}
