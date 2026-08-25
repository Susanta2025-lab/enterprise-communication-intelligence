import { Link } from "react-router-dom";

import { BACK_TO_DASHBOARD_LABEL } from "../../errors/copy";
import { DASHBOARD_PATH } from "../../navigation/paths";

type MailboxUnavailableStateProps = {
  title: string;
  message: string;
};

export function MailboxUnavailableState({ title, message }: MailboxUnavailableStateProps) {
  return (
    <div
      role="status"
      className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"
      data-testid="mailbox-unavailable"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1 min-w-0 break-words">{message}</p>
      <Link to={DASHBOARD_PATH} className="mt-3 inline-block text-sm font-medium text-amber-950 underline">
        {BACK_TO_DASHBOARD_LABEL}
      </Link>
    </div>
  );
}
