export type Due = { kind: "none" } | { kind: "date"; date: string; timezone: string } | { kind: "datetime"; at: string; timezone: string };
export type WorkStatus = "open" | "in_progress" | "completed" | "cancelled";
export type WorkFields = { title: string; description: string | null; due: Due; business_context_id: string | null };
export type WorkItem = WorkFields & {
  id: string; kind: "action" | "obligation"; status: WorkStatus; version: number;
  creation_origin: "manual" | "ai_confirmed"; created_at: string; updated_at: string;
  archived_at: string | null; completed_at: string | null; cancelled_at: string | null;
  confirmed_at: string | null; overdue: boolean;
};
export type WorkSource = {
  source_kind: string; analysis_id: string | null; attachment_analysis_id: string | null;
  connector_account_id: string | null; provider_message_id: string | null;
  provider_attachment_id: string | null; candidate_field: string | null;
  candidate_index: number | null; availability: "available" | "unavailable";
  provider_content_verified: false;
};
export type WorkDetail = WorkItem & { sources: WorkSource[] };
export type WorkEvent = { id: string; work_item_id: string; event_type: string; occurred_at: string; item_version: number; event_ordinal: number; context_at_event_id: string | null; metadata: { status?: WorkStatus; old_status?: WorkStatus; new_status?: WorkStatus; changed_fields?: ("title" | "description" | "due")[]; due?: Due; old_due?: Due | null; new_due?: Due | null; from_context_id?: string | null; to_context_id?: string | null; creation_origin?: WorkItem["creation_origin"] } };
export type Page<T> = { items: T[]; limit: number; offset: number };
export type WorkQuery = {
  limit?: number; offset?: number; kind?: WorkItem["kind"]; status?: WorkStatus;
  archive?: "active" | "archived" | "all"; business_context_id?: string; unassociated?: boolean;
  due_kind?: Due["kind"]; due_date_from?: string; due_date_to?: string;
  due_at_from?: string; due_at_to?: string; overdue?: boolean; sort?: "created_desc" | "due_asc";
};
export type CandidateLocator = { projection_version: 1; source_kind: "communication_analysis" | "attachment_analysis"; source_id: string; field: "action_items" | "potential_action_mentions" | "potential_dates"; index: number; digest: string };
export type Candidate = { candidate: CandidateLocator; value: string | Record<string, unknown>; advisory: true; truncated: boolean; warnings: string[]; limitations: string[] };
export type CandidateQuery = Pick<CandidateLocator, "source_kind" | "source_id"> & { limit?: number; offset?: number };
export type WorkCreate = WorkFields & { kind: WorkItem["kind"]; creation_key: string };
export type WorkConfirm = WorkCreate & { candidate: CandidateLocator; confirmed: true };
export function workParams(query: WorkQuery | CandidateQuery): string {
  return new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString();
}
export function ownedWorkLocation(location: string | null): string | null {
  const match = location?.match(/^\/api\/v1\/work-items\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i);
  return match ? `/tracking/${match[1]}` : null;
}
