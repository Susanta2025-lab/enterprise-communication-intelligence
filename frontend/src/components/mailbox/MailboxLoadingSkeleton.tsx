export function MailboxLoadingSkeleton() {
  return (
    <div role="status" aria-live="polite" aria-busy="true" data-testid="mailbox-loading">
      <p className="text-sm text-slate-600">Loading mailbox messages</p>
      <div className="mt-4 space-y-2">
        <div className="h-16 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
        <div className="h-16 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
        <div className="h-16 animate-pulse rounded-md border border-slate-200 bg-slate-100" />
      </div>
    </div>
  );
}
