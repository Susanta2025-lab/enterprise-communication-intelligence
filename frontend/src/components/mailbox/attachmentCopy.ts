export const ATTACHMENTS_HEADING = "Attachments";
export const ANALYZE_ATTACHMENT_LABEL = "Analyze attachment";
export const ANALYZING_ATTACHMENT_COPY = "Analyzing attachment";
export const ATTACHMENT_PRIVACY_COPY =
  "Attachments are accessed only when you choose Analyze attachment. The selected file may be temporarily processed and its content may be sent to the configured AI provider.";
export const ATTACHMENT_ANALYZE_PERMISSION_HINT =
  "Analyzing attachments requires the communications:analyze permission.";
export const NO_ATTACHMENTS_COPY = "This message has no attachments.";
export const ATTACHMENT_METADATA_LOADING_COPY = "Loading attachment details";
export const ATTACHMENT_TRUNCATED_LIST_COPY =
  "Additional attachments may exist. Only the returned metadata is shown.";
export const NOT_ANALYZED_STATUS = "Not analyzed";
export const UNSUPPORTED_STATUS = "Unsupported for analysis";
export const TOO_LARGE_STATUS = "Too large to analyze";
export const INLINE_STATUS = "Inline";
export const COMPLETED_STATUS = "Analyzed";
export const TRUNCATION_INDICATOR = "Analysis used a bounded portion of the document.";
export const PREVIOUS_ANALYSES_HEADING = "Previous analyses";
export const UNNAMED_ATTACHMENT_LABEL = "Untitled attachment";
export const ATTACHMENT_RESULT_HEADING = "Attachment analysis";
export const ATTACHMENT_RESULT_BOUNDARY =
  "Attachment analysis is informational only. It cannot propose, approve, execute, or send a reply.";

export function displayAttachmentFilename(filename: string | null | undefined): string {
  const trimmed = filename?.trim();
  return trimmed ? trimmed : UNNAMED_ATTACHMENT_LABEL;
}
