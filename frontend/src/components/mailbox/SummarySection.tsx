import { SUMMARY_UNAVAILABLE_COPY } from "./copy";

type SummarySectionProps = {
  text: string | null | undefined;
};

export function SummarySection({ text }: SummarySectionProps) {
  const summary = text?.trim();

  return (
    <section aria-labelledby="analysis-summary-heading">
      <h4 id="analysis-summary-heading" className="text-sm font-semibold text-slate-900">
        Summary
      </h4>
      <p className={summary ? "mt-2 text-sm text-slate-800" : "mt-2 text-sm italic text-slate-500"}>
        {summary || SUMMARY_UNAVAILABLE_COPY}
      </p>
    </section>
  );
}
