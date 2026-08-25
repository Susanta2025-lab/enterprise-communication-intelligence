import { REFRESH_STATUS_LABEL } from "../../errors/copy";

export const NO_SUBJECT_LABEL = "(No subject)";

export function displaySubject(subject: string | null | undefined): string {
  if (!subject || !subject.trim()) {
    return NO_SUBJECT_LABEL;
  }
  return subject;
}

export const ANALYZE_ACTION_LABEL = "Analyze message";
export const REANALYZE_ACTION_LABEL = "Re-analyze message";
export const ANALYZE_PERMISSION_HINT =
  "Analyzing messages requires the communications:analyze permission.";
export const NO_ACTION_ITEMS_COPY = "No action items identified.";
export const NO_DRAFT_COPY = "No draft suggestion was generated.";
export const SUMMARY_UNAVAILABLE_COPY = "Summary is unavailable.";
export const DRAFT_SUGGESTION_HEADING = "AI draft suggestion";
export const DRAFT_BOUNDARY_COPY = "AI-generated suggestion. Not approved or sent.";

const PRIORITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const CATEGORY_LABELS: Record<string, string> = {
  general: "General",
  request: "Request",
  incident: "Incident",
  approval: "Approval",
  notification: "Notification",
  inquiry: "Inquiry",
  other: "Other",
};

export function priorityLabel(level: string | null | undefined): string {
  if (!level) {
    return "Unavailable";
  }
  return PRIORITY_LABELS[level] ?? level;
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) {
    return "Unavailable";
  }
  return CATEGORY_LABELS[category] ?? category;
}

export const PROPOSE_REPLY_LABEL = "Propose reply";
export const APPROVE_REPLY_LABEL = "Approve reply";
export const REJECT_REPLY_LABEL = "Reject reply";
export const SEND_APPROVED_REPLY_LABEL = "Send approved reply";
export const REFRESH_WORKFLOW_STATUS_LABEL = REFRESH_STATUS_LABEL;
export const WORKFLOW_REVIEW_HEADING = "Workflow review";
export const WORKFLOW_PROPOSAL_HEADING = "Workflow proposal";
export const PROPOSED_REPLY_HEADING = "Proposed reply";
export const APPROVED_REPLY_HEADING = "Approved reply";
export const WORKFLOW_SNAPSHOT_BOUNDARY =
  "Workflow snapshot. This text is not editable and is not sent until you approve and confirm send.";
export const APPROVED_SNAPSHOT_BOUNDARY =
  "Approved communication. This text is not editable. Sending requires a separate confirmation.";
export const WORKFLOW_PERMISSION_HINT =
  "Proposing and reviewing replies requires the communications:workflow permission.";
export const SEND_PERMISSION_HINT =
  "Sending an approved reply requires the communications:send permission.";
export const ANALYSIS_NOT_PROPOSABLE_COPY = "This analysis cannot be proposed for sending.";
export const ANALYSIS_NO_DRAFT_COPY = "This analysis has no draft suggestion to propose.";
export const EXECUTION_UNCERTAIN_TITLE = "Sending status is uncertain.";
export const EXECUTION_UNCERTAIN_COPY =
  "The request may have reached the provider. Do not send again.";
export const SEND_IN_PROGRESS_COPY = "Sending the approved reply";
export const EXECUTED_SUCCESS_COPY = "Reply sent";
export const FAILED_TERMINAL_COPY =
  "Send could not be completed. This action cannot be sent again.";
export const REJECTED_TERMINAL_COPY =
  "This reply was rejected. It cannot be sent. Re-analyze the message to propose a new reply.";
export const SEND_CONFIRM_TITLE = "Send approved reply?";
export const SEND_CONFIRM_DESCRIPTION =
  "This will send the approved reply through the connected mailbox. This action may not be reversible.";
export const SEND_NOT_EXECUTABLE_COPY =
  "This reply cannot be sent through the current mailbox connection.";
export const PENDING_REVIEW_LABEL = "Pending review";
export const APPROVED_STATUS_LABEL = "Approved";
export const REJECTED_STATUS_LABEL = "Rejected";
export const EXECUTING_STATUS_LABEL = "Sending status is uncertain";
export const EXECUTED_STATUS_LABEL = "Reply sent";
export const FAILED_STATUS_LABEL = "Send could not be completed";
export const PROPOSE_IN_PROGRESS_COPY = "Proposing reply";
export const APPROVE_IN_PROGRESS_COPY = "Approving reply";
export const REJECT_IN_PROGRESS_COPY = "Rejecting reply";

export function workflowStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return PENDING_REVIEW_LABEL;
    case "approved":
      return APPROVED_STATUS_LABEL;
    case "rejected":
      return REJECTED_STATUS_LABEL;
    case "executing":
      return EXECUTING_STATUS_LABEL;
    case "executed":
      return EXECUTED_STATUS_LABEL;
    case "failed":
      return FAILED_STATUS_LABEL;
    default:
      return "Unknown status";
  }
}
