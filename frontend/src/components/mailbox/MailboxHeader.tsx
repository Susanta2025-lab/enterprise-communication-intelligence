import { Link } from "react-router-dom";

import { BACK_TO_DASHBOARD_LABEL, REFRESH_LABEL } from "../../errors/copy";
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
      <div className="min-w-0">
        <nav aria-label="Mailbox">
          <Link to={DASHBOARD_PATH} className="text-sm font-medium text-slate-700 underline">
            {BACK_TO_DASHBOARD_LABEL}
          </Link>
        </nav>
        <h2 id="mailbox-workspace-heading" className="mt-2 text-lg font-semibold break-words text-slate-900">
          {title}
        </h2>
      </div>
      {onRefresh ? (
        <Button
          className="w-full sm:w-auto"
          onClick={onRefresh}
          disabled={refreshDisabled}
          aria-busy={refreshing}
        >
          {REFRESH_LABEL}
        </Button>
      ) : null}
    </div>
  );
}
