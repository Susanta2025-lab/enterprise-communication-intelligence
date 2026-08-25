import { Link } from "react-router-dom";

import { DASHBOARD_PATH } from "../../navigation/paths";

type MailboxUnavailableStateProps = {
  title: string;
  message: string;
};

export function MailboxUnavailableState({ title, message }: MailboxUnavailableStateProps) {
  return (
    <div
      className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"
      data-testid="mailbox-unavailable"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1">{message}</p>
      <Link to={DASHBOARD_PATH} className="mt-3 inline-block text-sm font-medium text-amber-950 underline">
        Back to connected mailboxes
      </Link>
    </div>
  );
}
