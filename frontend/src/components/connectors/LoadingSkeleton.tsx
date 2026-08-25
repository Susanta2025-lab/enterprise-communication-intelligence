export function LoadingSkeleton() {
  return (
    <div role="status" aria-live="polite" className="space-y-4" data-testid="connector-loading">
      <p className="text-sm text-slate-600">Loading connector accounts</p>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-40 animate-pulse rounded-lg border border-slate-200 bg-slate-100" />
        <div className="h-40 animate-pulse rounded-lg border border-slate-200 bg-slate-100" />
      </div>
    </div>
  );
}
