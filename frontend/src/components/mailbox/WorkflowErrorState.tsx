import { forwardRef } from "react";
import { Link } from "react-router-dom";

import { DASHBOARD_PATH } from "../../navigation/paths";
import { Button } from "../ui/button";

type WorkflowErrorStateProps = {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  showDashboardLink?: boolean;
};

export const WorkflowErrorState = forwardRef<HTMLDivElement, WorkflowErrorStateProps>(
  function WorkflowErrorState(
    { message, onRetry, retryLabel = "Retry", showDashboardLink = false },
    ref,
  ) {
    return (
      <div
        ref={ref}
        role="alert"
        tabIndex={-1}
        className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-red-800"
      >
        <p>{message}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {onRetry ? <Button onClick={onRetry}>{retryLabel}</Button> : null}
          {showDashboardLink ? (
            <Link to={DASHBOARD_PATH} className="text-sm font-medium text-red-900 underline">
              Back to connected mailboxes
            </Link>
          ) : null}
        </div>
      </div>
    );
  },
);
