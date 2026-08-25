export const WORKFLOW_ACTIONS_PATH = "/api/v1/workflow-actions";

export type WorkflowActionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executing"
  | "executed"
  | "failed";

export type WorkflowActionType = "reply";

export type WorkflowActionResponse = {
  id: string;
  action_type: WorkflowActionType;
  analysis_id: string;
  status: WorkflowActionStatus;
  proposed_reply_body: string;
  approved_reply_body: string | null;
  created_at: string;
  approved_at: string | null;
  rejected_at: string | null;
  executed_at: string | null;
  failed_at: string | null;
  has_execution_target: boolean;
};

export type CreateWorkflowActionQuery = {
  analysisId: string;
};

export function workflowActionPath(actionId: string): string {
  return `${WORKFLOW_ACTIONS_PATH}/${actionId}`;
}

export function workflowActionApprovePath(actionId: string): string {
  return `${workflowActionPath(actionId)}/approve`;
}

export function workflowActionRejectPath(actionId: string): string {
  return `${workflowActionPath(actionId)}/reject`;
}

export function workflowActionExecutePath(actionId: string): string {
  return `${workflowActionPath(actionId)}/execute`;
}

export function isPendingWorkflow(status: WorkflowActionStatus): boolean {
  return status === "pending";
}

export function isApprovedWorkflow(status: WorkflowActionStatus): boolean {
  return status === "approved";
}

export function isExecutingWorkflow(status: WorkflowActionStatus): boolean {
  return status === "executing";
}
