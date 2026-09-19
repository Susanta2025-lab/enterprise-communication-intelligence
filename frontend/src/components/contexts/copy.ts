import type { BusinessContextType, ContextTimelineEventType } from "../../api/contexts";

export const CONTEXT_TYPE_OPTIONS: readonly BusinessContextType[] = [
  "matter",
  "case",
  "project",
  "client",
  "transaction",
  "account",
  "other",
] as const;

export function contextTypeLabel(type: BusinessContextType): string {
  switch (type) {
    case "matter":
      return "Matter";
    case "case":
      return "Case";
    case "project":
      return "Project";
    case "client":
      return "Client";
    case "transaction":
      return "Transaction";
    case "account":
      return "Account";
    case "other":
      return "Other";
  }
}

export function contextStatusLabel(status: "active" | "archived"): string {
  return status === "active" ? "Active" : "Archived";
}

export function timelineEventLabel(type: ContextTimelineEventType): string {
  switch (type) {
    case "context_created":
      return "Context created";
    case "context_archived":
      return "Context archived";
    case "communication_associated":
      return "Communication associated";
    case "analysis_completed":
      return "Analysis completed";
    case "attachment_analysis_completed":
      return "Attachment analysis completed";
    case "workflow_proposed":
      return "Workflow proposed";
    case "workflow_approved":
      return "Workflow approved";
    case "workflow_rejected":
      return "Workflow rejected";
    case "workflow_executed":
      return "Workflow executed";
    case "workflow_failed":
      return "Workflow failed";
  }
}

export const TITLE_MAX = 200;
export const DESCRIPTION_MAX = 4000;
export const REFERENCE_MAX = 128;

export const ARCHIVE_COPY =
  "Archive hides this context from the default list. It does not delete messages, attachments, analyses, or workflows.";

export const RESTORE_COPY =
  "Restore makes this context active again so you can associate communications.";

export const REMOVE_ASSOCIATION_COPY =
  "Remove from Context deletes only the association. It does not delete the email or any analyses.";
