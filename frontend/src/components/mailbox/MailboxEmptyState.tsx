export function MailboxEmptyState() {
  return (
    <p className="text-sm text-slate-600" data-testid="mailbox-empty" role="status">
      No recent messages were returned.
    </p>
  );
}
