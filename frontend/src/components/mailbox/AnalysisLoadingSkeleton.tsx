type AnalysisLoadingSkeletonProps = {
  reanalyzing?: boolean;
};

export function AnalysisLoadingSkeleton({ reanalyzing = false }: AnalysisLoadingSkeletonProps) {
  if (reanalyzing) {
    return (
      <p role="status" aria-live="polite" aria-busy="true" className="text-sm text-slate-600">
        Analyzing again…
      </p>
    );
  }

  return (
    <div role="status" aria-live="polite" aria-busy="true" data-testid="analysis-loading">
      <p className="text-sm text-slate-600">Analyzing message</p>
      <div className="mt-3 space-y-2">
        <div className="h-16 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
        <div className="h-10 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
        <div className="h-24 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
      </div>
    </div>
  );
}
