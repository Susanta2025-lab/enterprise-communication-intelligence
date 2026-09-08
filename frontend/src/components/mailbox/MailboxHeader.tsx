import { Link } from "react-router-dom";

import { BACK_TO_DASHBOARD_LABEL, REFRESH_LABEL } from "../../errors/copy";
import { DASHBOARD_PATH } from "../../navigation/paths";
import { ConnectorLogo } from "../connectors/ConnectorLogo";
import { Button } from "../ui/button";

type MailboxHeaderProps = {
  title: string;
  provider?: string;
  onRefresh?: () => void;
  refreshDisabled?: boolean;
  refreshing?: boolean;
};

export function MailboxHeader({
  title,
  provider,
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
        <div className="mt-2 flex min-w-0 items-center gap-2.5">
          {provider ? (
            <ConnectorLogo provider={provider} className="h-7 w-7 shrink-0" />
          ) : null}
          <h2 id="mailbox-workspace-heading" className="text-lg font-semibold break-words text-slate-900">
            {title}
          </h2>
        </div>
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
