export const ATTACHMENT_ANALYSES_PATH = "/api/v1/attachment-analyses";
export const MAX_ATTACHMENT_CONTENT_BYTES = 5 * 1024 * 1024;

export function connectorAccountAttachmentsPath(connectorAccountId: string): string {
  return `/api/v1/connector-accounts/${connectorAccountId}/messages/attachments`;
}

export function connectorAccountAttachmentAnalyzePath(connectorAccountId: string): string {
  return `${connectorAccountAttachmentsPath(connectorAccountId)}/analyze`;
}

export function attachmentAnalysisPath(attachmentAnalysisId: string): string {
  return `${ATTACHMENT_ANALYSES_PATH}/${attachmentAnalysisId}`;
}

export type AttachmentDisposition = "attachment" | "inline" | "unknown";

export type AttachmentKind = "pdf" | "docx" | "jpeg" | "png" | "txt" | "xlsx";

export type AttachmentExtractedContentStatus = "text" | "truncated_text" | "image";

export type AttachmentMetadataItem = {
  provider_attachment_id: string;
  filename: string;
  media_type: string;
  reported_size: number;
  is_inline: boolean;
  disposition: AttachmentDisposition;
};

export type AttachmentMetadataListResponse = {
  items: readonly AttachmentMetadataItem[];
  truncated: boolean;
};

export type ListMailboxAttachmentsQuery = {
  connectorAccountId: string;
  providerMessageId: string;
};

export type AnalyzeMailboxAttachmentQuery = {
  connectorAccountId: string;
  providerMessageId: string;
  providerAttachmentId: string;
};

export type AttachmentAnalysisSummary = {
  text: string;
  confidence?: number | null;
};

export type AttachmentAnalysisPriority = {
  level: "low" | "medium" | "high" | "critical";
  rationale?: string | null;
  confidence?: number | null;
};

export type AttachmentAnalysisActionItem = {
  description: string;
  owner?: string | null;
  due_at?: string | null;
  priority?: "low" | "medium" | "high" | "critical" | null;
};

export type TabularSheetSummary = {
  sheet_name: string;
  summary: string;
};

// Advisory observations from the backend; never workflow or deadline entities.
export type TabularAnalysisResult = {
  summary: string;
  sheet_summaries: readonly TabularSheetSummary[];
  important_fields: readonly string[];
  notable_values_or_patterns: readonly string[];
  data_quality_observations: readonly string[];
  potential_dates: readonly string[];
  potential_amounts: readonly string[];
  potential_action_mentions: readonly string[];
  warnings: readonly string[];
  limitations: readonly string[];
  source_truncated: boolean;
  provider?: string | null;
};

export type AttachmentAnalysisResponse = {
  attachment_analysis_id: string;
  created_at: string;
  connector_account_id: string;
  provider_message_id: string;
  provider_attachment_id: string;
  filename: string;
  media_type: string;
  kind: AttachmentKind;
  extracted_content_status: AttachmentExtractedContentStatus;
  truncated: boolean;
  warnings: readonly string[];
  page_count?: number | null;
  summary: AttachmentAnalysisSummary;
  priority: AttachmentAnalysisPriority;
  category?: string;
  action_items?: readonly AttachmentAnalysisActionItem[];
  provider?: string | null;
  tabular_result?: TabularAnalysisResult | null;
};

export type AttachmentAnalysisListResponse = {
  items: readonly AttachmentAnalysisResponse[];
  limit: number;
  offset: number;
};

export type ListAttachmentAnalysesQuery = {
  limit?: number;
  offset?: number;
  connectorAccountId?: string;
  providerMessageId?: string;
};
