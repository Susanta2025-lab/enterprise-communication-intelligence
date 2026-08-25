import { Button } from "../ui/button";
import {
  APPROVE_REPLY_LABEL,
  PROPOSE_REPLY_LABEL,
  REFRESH_WORKFLOW_STATUS_LABEL,
  REJECT_REPLY_LABEL,
  SEND_APPROVED_REPLY_LABEL,
  SEND_NOT_EXECUTABLE_COPY,
  SEND_PERMISSION_HINT,
  WORKFLOW_PERMISSION_HINT,
} from "./copy";

type WorkflowActionsProps = {
  canWorkflow: boolean;
  canSend: boolean;
  showPropose: boolean;
  showApproveReject: boolean;
  showSend: boolean;
  sendDisabledReason: "permission" | "not_executable" | null;
  proposePending: boolean;
  approvePending: boolean;
  rejectPending: boolean;
  executePending: boolean;
  refreshPending: boolean;
  showRefresh: boolean;
  onPropose: () => void;
  onApprove: () => void;
  onReject: () => void;
  onSend: () => void;
  onRefresh: () => void;
};

export function WorkflowActions({
  canWorkflow,
  canSend,
  showPropose,
  showApproveReject,
  showSend,
  sendDisabledReason,
  proposePending,
  approvePending,
  rejectPending,
  executePending,
  refreshPending,
  showRefresh,
  onPropose,
  onApprove,
  onReject,
  onSend,
  onRefresh,
}: WorkflowActionsProps) {
  const reviewBusy = approvePending || rejectPending;
  const sendBusy = executePending;

  return (
    <div className="space-y-3">
      {showPropose ? (
        <div>
          <Button
            onClick={onPropose}
            disabled={!canWorkflow || proposePending}
            aria-busy={proposePending}
            aria-describedby={canWorkflow ? undefined : "workflow-permission-hint"}
          >
            {PROPOSE_REPLY_LABEL}
          </Button>
          {canWorkflow ? null : (
            <p id="workflow-permission-hint" className="mt-2 text-sm text-slate-600">
              {WORKFLOW_PERMISSION_HINT}
            </p>
          )}
        </div>
      ) : null}

      {showApproveReject ? (
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={onApprove}
            disabled={!canWorkflow || reviewBusy}
            aria-busy={approvePending}
            aria-describedby={canWorkflow ? undefined : "workflow-review-permission-hint"}
          >
            {APPROVE_REPLY_LABEL}
          </Button>
          <Button
            className="bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50"
            onClick={onReject}
            disabled={!canWorkflow || reviewBusy}
            aria-busy={rejectPending}
            aria-describedby={canWorkflow ? undefined : "workflow-review-permission-hint"}
          >
            {REJECT_REPLY_LABEL}
          </Button>
          {canWorkflow ? null : (
            <p id="workflow-review-permission-hint" className="basis-full text-sm text-slate-600">
              {WORKFLOW_PERMISSION_HINT}
            </p>
          )}
        </div>
      ) : null}

      {showSend ? (
        <div>
          <Button
            onClick={onSend}
            disabled={!canSend || sendBusy || sendDisabledReason === "not_executable"}
            aria-busy={sendBusy}
            aria-describedby={
              sendDisabledReason === "permission"
                ? "send-permission-hint"
                : sendDisabledReason === "not_executable"
                  ? "send-not-executable-hint"
                  : undefined
            }
          >
            {SEND_APPROVED_REPLY_LABEL}
          </Button>
          {sendDisabledReason === "permission" ? (
            <p id="send-permission-hint" className="mt-2 text-sm text-slate-600">
              {SEND_PERMISSION_HINT}
            </p>
          ) : null}
          {sendDisabledReason === "not_executable" ? (
            <p id="send-not-executable-hint" className="mt-2 text-sm text-slate-600">
              {SEND_NOT_EXECUTABLE_COPY}
            </p>
          ) : null}
        </div>
      ) : null}

      {showRefresh ? (
        <Button
          className="bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50"
          onClick={onRefresh}
          disabled={refreshPending || sendBusy}
          aria-busy={refreshPending}
        >
          {REFRESH_WORKFLOW_STATUS_LABEL}
        </Button>
      ) : null}
    </div>
  );
}
