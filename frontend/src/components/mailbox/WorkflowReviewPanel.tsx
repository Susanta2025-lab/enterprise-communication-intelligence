import { useEffect, useRef, useState } from "react";

import { EciApiError } from "../../api/errors";
import {
  isApprovedWorkflow,
  isExecutingWorkflow,
  isPendingWorkflow,
} from "../../api/workflowActions";
import type { useWorkflowAction } from "../../hooks/useWorkflowAction";
import { ExecutionUncertainState } from "./ExecutionUncertainState";
import { SendConfirmationDialog } from "./SendConfirmationDialog";
import { WorkflowActions } from "./WorkflowActions";
import { WorkflowErrorState } from "./WorkflowErrorState";
import { WorkflowSnapshot } from "./WorkflowSnapshot";
import { WorkflowStatusBadge } from "./WorkflowStatusBadge";
import {
  ANALYSIS_NO_DRAFT_COPY,
  ANALYSIS_NOT_PROPOSABLE_COPY,
  executeErrorMessage,
  executeRetryLabel,
  FAILED_TERMINAL_COPY,
  proposeErrorMessage,
  proposeRetryLabel,
  REFRESH_WORKFLOW_STATUS_LABEL,
  refreshWorkflowErrorMessage,
  REJECTED_TERMINAL_COPY,
  reviewErrorMessage,
  reviewRetryLabel,
  SEND_IN_PROGRESS_COPY,
  SEND_PERMISSION_HINT,
  WORKFLOW_PROPOSAL_HEADING,
  WORKFLOW_REVIEW_HEADING,
} from "./copy";

type WorkflowSession = ReturnType<typeof useWorkflowAction>;

type WorkflowReviewPanelProps = {
  analysisId: string | null;
  hasDraft: boolean;
  canWorkflow: boolean;
  canSend: boolean;
  workflow: WorkflowSession;
};

export function WorkflowReviewPanel({
  analysisId,
  hasDraft,
  canWorkflow,
  canSend,
  workflow,
}: WorkflowReviewPanelProps) {
  const [sendConfirmOpen, setSendConfirmOpen] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const action = workflow.action;
  const status = action?.status;
  const proposable = Boolean(analysisId) && hasDraft;
  const showPropose = action === null && proposable;
  const showApproveReject = status !== undefined && isPendingWorkflow(status);
  const approved = status !== undefined && isApprovedWorkflow(status);
  const executing = status !== undefined && isExecutingWorkflow(status);
  const uncertain = workflow.executionUncertain || executing;
  const showSend = approved && canSend && !uncertain && !workflow.executePending;
  const sendDisabledReason = approved && action && !action.has_execution_target ? "not_executable" : null;
  const showRefresh =
    Boolean(action) &&
    !uncertain &&
    (workflow.errorOperation === "execute" || workflow.errorOperation === "refresh");

  useEffect(() => {
    if (workflow.error) {
      errorRef.current?.focus();
    }
  }, [workflow.error]);

  const errorMessage = workflowErrorCopy(workflow);
  const retry = workflowRetry(workflow);
  const showDashboardLink =
    workflow.error instanceof EciApiError &&
    workflow.errorOperation === "execute" &&
    workflow.error.status === 409;

  return (
    <section className="space-y-4 border-t border-slate-200 pt-5" aria-labelledby="workflow-review-heading">
      <h3 id="workflow-review-heading" className="text-base font-semibold text-slate-900">
        {WORKFLOW_REVIEW_HEADING}
      </h3>

      {!analysisId ? <p className="text-sm text-slate-600">{ANALYSIS_NOT_PROPOSABLE_COPY}</p> : null}
      {analysisId && !hasDraft && action === null ? (
        <p className="text-sm text-slate-600">{ANALYSIS_NO_DRAFT_COPY}</p>
      ) : null}

      {action ? (
        <div className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">{WORKFLOW_PROPOSAL_HEADING}</h4>
            <div className="mt-2">
              <WorkflowStatusBadge status={uncertain && !executing ? "executing" : action.status} />
            </div>
          </div>
          <WorkflowSnapshot
            variant={action.status === "pending" || action.status === "rejected" ? "proposed" : "approved"}
            body={
              action.status === "pending" || action.status === "rejected"
                ? action.proposed_reply_body
                : (action.approved_reply_body ?? action.proposed_reply_body)
            }
          />
          {action.status === "rejected" ? (
            <p role="status" className="text-sm text-slate-700">
              {REJECTED_TERMINAL_COPY}
            </p>
          ) : null}
          {action.status === "failed" ? (
            <p role="alert" className="text-sm text-slate-700">
              {FAILED_TERMINAL_COPY}
            </p>
          ) : null}
        </div>
      ) : null}

      {workflow.executePending ? (
        <p role="status" aria-live="polite" aria-busy="true" className="text-sm text-slate-600">
          {SEND_IN_PROGRESS_COPY}
        </p>
      ) : null}

      {uncertain && !workflow.executePending ? (
        <ExecutionUncertainState onRefresh={workflow.refresh} refreshPending={workflow.refreshPending} />
      ) : null}

      {errorMessage && !uncertain ? (
        <WorkflowErrorState
          ref={errorRef}
          message={errorMessage}
          onRetry={retry ? () => retry.action() : undefined}
          retryLabel={retry?.label}
          showDashboardLink={showDashboardLink}
        />
      ) : null}

      {approved && !canSend && !uncertain ? (
        <p className="text-sm text-slate-600">{SEND_PERMISSION_HINT}</p>
      ) : null}

      <WorkflowActions
        canWorkflow={canWorkflow}
        canSend={canSend}
        showPropose={showPropose}
        showApproveReject={showApproveReject}
        showSend={showSend}
        sendDisabledReason={sendDisabledReason}
        proposePending={workflow.proposePending}
        approvePending={workflow.approvePending}
        rejectPending={workflow.rejectPending}
        executePending={workflow.executePending}
        refreshPending={workflow.refreshPending}
        showRefresh={showRefresh && !uncertain}
        onPropose={workflow.propose}
        onApprove={workflow.approve}
        onReject={workflow.reject}
        onSend={() => setSendConfirmOpen(true)}
        onRefresh={workflow.refresh}
      />

      <SendConfirmationDialog
        open={sendConfirmOpen}
        busy={workflow.executePending}
        onCancel={() => setSendConfirmOpen(false)}
        onConfirm={() => {
          workflow.execute();
          setSendConfirmOpen(false);
        }}
      />
    </section>
  );
}

function workflowErrorCopy(workflow: WorkflowSession): string | null {
  if (!workflow.error) {
    return null;
  }
  if (workflow.errorOperation === "propose") {
    return proposeErrorMessage(workflow.error);
  }
  if (workflow.errorOperation === "approve" || workflow.errorOperation === "reject") {
    return reviewErrorMessage(workflow.error);
  }
  if (workflow.errorOperation === "execute") {
    return executeErrorMessage(workflow.error);
  }
  if (workflow.errorOperation === "refresh") {
    return refreshWorkflowErrorMessage(workflow.error);
  }
  return null;
}

function workflowRetry(workflow: WorkflowSession): { label: string; action: () => void } | null {
  if (!workflow.error) {
    return null;
  }
  if (workflow.errorOperation === "propose") {
    const label = proposeRetryLabel(workflow.error);
    return label ? { label, action: workflow.propose } : null;
  }
  if (workflow.errorOperation === "approve") {
    const label = reviewRetryLabel(workflow.error);
    if (!label) {
      return null;
    }
    return {
      label,
      action: label === REFRESH_WORKFLOW_STATUS_LABEL ? workflow.refresh : workflow.approve,
    };
  }
  if (workflow.errorOperation === "reject") {
    const label = reviewRetryLabel(workflow.error);
    if (!label) {
      return null;
    }
    return {
      label,
      action: label === REFRESH_WORKFLOW_STATUS_LABEL ? workflow.refresh : workflow.reject,
    };
  }
  if (workflow.errorOperation === "execute") {
    const label = executeRetryLabel(workflow.error);
    return label ? { label, action: workflow.refresh } : null;
  }
  return null;
}
