import { Button } from "../ui/button";
import { EXECUTION_UNCERTAIN_COPY, EXECUTION_UNCERTAIN_TITLE, REFRESH_WORKFLOW_STATUS_LABEL } from "./copy";

type ExecutionUncertainStateProps = {
  onRefresh?: () => void;
  refreshPending?: boolean;
};

export function ExecutionUncertainState({
  onRefresh,
  refreshPending = false,
}: ExecutionUncertainStateProps) {
  return (
    <div
      role="alert"
      className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"
    >
      <p className="font-semibold">{EXECUTION_UNCERTAIN_TITLE}</p>
      <p className="mt-1">{EXECUTION_UNCERTAIN_COPY}</p>
      {onRefresh ? (
        <Button
          className="mt-3 bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50"
          onClick={onRefresh}
          disabled={refreshPending}
          aria-busy={refreshPending}
        >
          {REFRESH_WORKFLOW_STATUS_LABEL}
        </Button>
      ) : null}
    </div>
  );
}
