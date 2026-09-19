/** Phase 20 BusinessContext API contracts and path helpers. */

export const CONTEXTS_PATH = "/api/v1/contexts";

export type BusinessContextType =
  | "matter"
  | "case"
  | "project"
  | "client"
  | "transaction"
  | "account"
  | "other";

export type BusinessContextStatus = "active" | "archived";

export type AssociationSource = "manual";

export type ContextMatchStrength = "high" | "medium" | "low";

export type ContextTimelineEventType =
  | "context_created"
  | "context_archived"
  | "communication_associated"
  | "analysis_completed"
  | "attachment_analysis_completed"
  | "workflow_proposed"
  | "workflow_approved"
  | "workflow_rejected"
  | "workflow_executed"
  | "workflow_failed";

export type BusinessContext = {
  id: string;
  type: BusinessContextType;
  title: string;
  description: string | null;
  reference: string | null;
  status: BusinessContextStatus;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type BusinessContextListResponse = {
  items: BusinessContext[];
  limit: number;
  offset: number;
};

export type BusinessContextCreateRequest = {
  type: BusinessContextType;
  title: string;
  description?: string | null;
  reference?: string | null;
};

export type BusinessContextUpdateRequest = {
  type?: BusinessContextType;
  title?: string;
  description?: string | null;
  reference?: string | null;
};

export type ListContextsQuery = {
  limit?: number;
  offset?: number;
  status?: BusinessContextStatus;
  type?: BusinessContextType;
  reference?: string;
  includeArchived?: boolean;
};

export type BusinessContextCommunicationLink = {
  id: string;
  business_context_id: string;
  connector_account_id: string;
  provider_message_id: string;
  analysis_id: string | null;
  associated_at: string;
  association_source: AssociationSource;
};

export type BusinessContextCommunicationLinkListResponse = {
  items: BusinessContextCommunicationLink[];
  limit: number;
  offset: number;
};

export type AssociateCommunicationRequest = {
  connector_account_id: string;
  provider_message_id: string;
  analysis_id?: string | null;
};

export type ContextSuggestionRequest = {
  connector_account_id: string;
  provider_message_id: string;
  analysis_id: string;
};

export type ContextSuggestionItem = {
  business_context_id: string;
  type: BusinessContextType;
  title: string;
  reference: string | null;
  match_strength: ContextMatchStrength;
  rationale: string;
};

export type ContextSuggestionListResponse = {
  suggestions: ContextSuggestionItem[];
  no_match_reason: string | null;
};

export type ContextTimelineEntry = {
  id: string;
  type: ContextTimelineEventType;
  occurred_at: string;
  title: string;
  summary: string | null;
  source_type: string | null;
  source_id: string | null;
  connector_account_id: string | null;
  provider_message_id: string | null;
};

export type ContextTimelineListResponse = {
  items: ContextTimelineEntry[];
  limit: number;
  offset: number;
};

export type ListContextTimelineQuery = {
  limit?: number;
  offset?: number;
};

export function contextPath(contextId: string): string {
  return `${CONTEXTS_PATH}/${contextId}`;
}

export function contextArchivePath(contextId: string): string {
  return `${contextPath(contextId)}/archive`;
}

export function contextRestorePath(contextId: string): string {
  return `${contextPath(contextId)}/restore`;
}

export function contextCommunicationsPath(contextId: string): string {
  return `${contextPath(contextId)}/communications`;
}

export function contextCommunicationLinkPath(contextId: string, linkId: string): string {
  return `${contextCommunicationsPath(contextId)}/${linkId}`;
}

export function contextTimelinePath(contextId: string): string {
  return `${contextPath(contextId)}/timeline`;
}

export function contextSuggestionsPath(): string {
  return `${CONTEXTS_PATH}/suggestions`;
}
