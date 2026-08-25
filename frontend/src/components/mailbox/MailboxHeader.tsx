import { Link } from "react-router-dom";

import { DASHBOARD_PATH } from "../../navigation/paths";
import { Button } from "../ui/button";

type MailboxHeaderProps = {
  title: string;
  onRefresh?: () => void;
  refreshDisabled?: boolean;
  refreshing?: boolean;
};

export function MailboxHeader({
  title,
  onRefresh,
  refreshDisabled,
  refreshing,
}: MailboxHeaderProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <Link to={DASHBOARD_PATH} className="text-sm font-medium text-slate-700 underline">
          Back to connected mailboxes
        </Link>
        <h2 id="mailbox-workspace-heading" className="mt-2 text-lg font-semibold text-slate-900">
          {title}
        </h2>
      </div>
      {onRefresh ? (
        <Button onClick={onRefresh} disabled={refreshDisabled} aria-busy={refreshing}>
          Refresh
        </Button>
      ) : null}
    </div>
  );
}
