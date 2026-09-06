import { SUMMARY_UNAVAILABLE_COPY } from "./copy";

type SummarySectionProps = {
  text: string | null | undefined;
  headingId?: string;
};

export function SummarySection({ text, headingId = "analysis-summary-heading" }: SummarySectionProps) {
  const summary = text?.trim();

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <h5 id={headingId} className="text-sm font-semibold text-slate-900">
        Summary
      </h5>
      <p
        className={
          summary
            ? "mt-2 min-w-0 break-words text-sm text-slate-800"
            : "mt-2 text-sm italic text-slate-500"
        }
      >
        {summary || SUMMARY_UNAVAILABLE_COPY}
      </p>
    </section>
  );
}
