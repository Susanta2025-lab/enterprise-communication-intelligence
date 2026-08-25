export const MAILBOX_UI_PAGE_SIZE = 10;

export type MailboxMessageListItem = {
  provider_message_id: string;
  sender: string;
  subject: string | null;
  sent_at: string | null;
  received_at: string | null;
};

export type MailboxMessageListResponse = {
  items: readonly MailboxMessageListItem[];
  next_cursor: string | null;
};

export type ListMailboxMessagesQuery = {
  connectorAccountId: string;
  pageSize?: number;
  cursor?: string;
};

export function connectorAccountMessagesPath(connectorAccountId: string): string {
  return `/api/v1/connector-accounts/${connectorAccountId}/messages`;
}

export function connectorAccountMessageAnalyzePath(connectorAccountId: string): string {
  return `${connectorAccountMessagesPath(connectorAccountId)}/analyze`;
}

export type PriorityLevel = "low" | "medium" | "high" | "critical";

export type MessageCategory =
  | "general"
  | "request"
  | "incident"
  | "approval"
  | "notification"
  | "inquiry"
  | "other";

export type AnalysisSummary = {
  text: string;
  confidence?: number | null;
};

export type AnalysisPriority = {
  level: PriorityLevel;
  rationale?: string | null;
  confidence?: number | null;
};

export type AnalysisActionItem = {
  description: string;
  owner?: string | null;
  due_at?: string | null;
  priority?: PriorityLevel | null;
};

export type AnalysisDraftReply = {
  body: string;
  tone?: string | null;
  confidence?: number | null;
};

export type CommunicationAnalysis = {
  summary: AnalysisSummary;
  priority: AnalysisPriority;
  category?: MessageCategory;
  action_items?: readonly AnalysisActionItem[];
  draft_reply?: AnalysisDraftReply | null;
  message_id?: string | null;
};

export type CommunicationAnalysisResponse = {
  analysis: CommunicationAnalysis;
  provider?: string | null;
  analysis_id?: string;
};

export type AnalyzeMailboxMessageQuery = {
  connectorAccountId: string;
  providerMessageId: string;
};
