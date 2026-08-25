import { DRAFT_BOUNDARY_COPY, DRAFT_SUGGESTION_HEADING, NO_DRAFT_COPY } from "./copy";

type DraftReplyPanelProps = {
  body: string | null | undefined;
};

export function DraftReplyPanel({ body }: DraftReplyPanelProps) {
  const draft = body?.trim();

  return (
    <section aria-labelledby="analysis-draft-heading" className="min-w-0">
      <h5 id="analysis-draft-heading" className="text-sm font-semibold text-slate-900">
        {DRAFT_SUGGESTION_HEADING}
      </h5>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        {DRAFT_BOUNDARY_COPY}
      </p>
      {draft ? (
        <pre className="mt-3 max-w-full min-w-0 overflow-x-hidden whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-slate-50 p-3 font-sans text-sm text-slate-800">
          {draft}
        </pre>
      ) : (
        <p className="mt-3 text-sm italic text-slate-500">{NO_DRAFT_COPY}</p>
      )}
    </section>
  );
}
