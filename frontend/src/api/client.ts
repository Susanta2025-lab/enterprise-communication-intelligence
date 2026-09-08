import type { AccessTokenProvider } from "../auth/tokenProvider";
import { InteractionRequiredError } from "../auth/tokenProvider";
import {
  connectorAccountDisconnectPath,
  connectorAccountReauthorizePath,
  connectAnotherAccountAuthorizePath,
  type AuthorizationStartResponse,
  type ConnectorAccountListResponse,
  type ConnectorProvider,
  type ListConnectorAccountsQuery,
} from "./connectorAccounts";
import {
  ATTACHMENT_ANALYSES_PATH,
  attachmentAnalysisPath,
  connectorAccountAttachmentAnalyzePath,
  connectorAccountAttachmentsPath,
  type AnalyzeMailboxAttachmentQuery,
  type AttachmentAnalysisListResponse,
  type AttachmentAnalysisResponse,
  type AttachmentMetadataListResponse,
  type ListAttachmentAnalysesQuery,
  type ListMailboxAttachmentsQuery,
} from "./attachments";
import {
  connectorAccountMessageAnalyzePath,
  connectorAccountMessagesPath,
  MAILBOX_UI_PAGE_SIZE,
  type AnalyzeMailboxMessageQuery,
  type CommunicationAnalysisResponse,
  type ListMailboxMessagesQuery,
  type MailboxMessageListResponse,
} from "./mailbox";
import {
  WORKFLOW_ACTIONS_PATH,
  workflowActionApprovePath,
  workflowActionExecutePath,
  workflowActionPath,
  workflowActionRejectPath,
  type CreateWorkflowActionQuery,
  type WorkflowActionResponse,
} from "./workflowActions";
import {
  CONNECTOR_ACCOUNTS_PATH,
  classifyAttachmentDetail,
  EciApiError,
  GMAIL_AUTHORIZE_PATH,
  MICROSOFT_GRAPH_AUTHORIZE_PATH,
  kindForStatus,
  messageForKind,
  PROTECTED_ANALYSES_SMOKE_PATH,
  type AnalysisListResponse,
} from "./errors";
import { HEALTH_PATH, type PlatformHealthResponse } from "./health";

type FetchLike = typeof fetch;

export type EciApiClientOptions = {
  baseUrl: string;
  tokenProvider: AccessTokenProvider;
  fetchImpl?: FetchLike;
  createRequestId?: () => string;
};

export class EciApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: AccessTokenProvider;
  private readonly fetchImpl: FetchLike;
  private readonly createRequestId: () => string;

  constructor(options: EciApiClientOptions) {
    this.baseUrl = options.baseUrl;
    this.tokenProvider = options.tokenProvider;
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.createRequestId = options.createRequestId ?? (() => crypto.randomUUID());
  }

  async getAnalysesSmoke(): Promise<AnalysisListResponse> {
    return this.requestJson<AnalysisListResponse>("GET", PROTECTED_ANALYSES_SMOKE_PATH);
  }

  async getPlatformHealth(): Promise<PlatformHealthResponse> {
    const response = await this.fetchImpl(new URL(HEALTH_PATH, `${this.baseUrl}/`).toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-Request-ID": this.createRequestId(),
      },
    });
    if (!response.ok) {
      const kind = kindForStatus(response.status);
      throw new EciApiError(response.status, kind, messageForKind(kind));
    }
    return (await response.json()) as PlatformHealthResponse;
  }

  async listConnectorAccounts(
    query: ListConnectorAccountsQuery = {},
  ): Promise<ConnectorAccountListResponse> {
    const params = new URLSearchParams();
    params.set("limit", String(query.limit ?? 20));
    params.set("offset", String(query.offset ?? 0));
    return this.requestJson<ConnectorAccountListResponse>(
      "GET",
      `${CONNECTOR_ACCOUNTS_PATH}?${params.toString()}`,
    );
  }

  async startGmailAuthorization(): Promise<AuthorizationStartResponse> {
    return this.requestJson<AuthorizationStartResponse>("POST", GMAIL_AUTHORIZE_PATH);
  }

  async startMicrosoftGraphAuthorization(): Promise<AuthorizationStartResponse> {
    return this.requestJson<AuthorizationStartResponse>("POST", MICROSOFT_GRAPH_AUTHORIZE_PATH);
  }

  async startConnectAnotherAccountAuthorization(
    provider: ConnectorProvider,
  ): Promise<AuthorizationStartResponse> {
    return this.requestJson<AuthorizationStartResponse>(
      "POST",
      connectAnotherAccountAuthorizePath(provider),
    );
  }

  async reauthorizeConnectorAccount(connectorAccountId: string): Promise<AuthorizationStartResponse> {
    return this.requestJson<AuthorizationStartResponse>(
      "POST",
      connectorAccountReauthorizePath(connectorAccountId),
    );
  }

  async disconnectConnectorAccount(connectorAccountId: string): Promise<void> {
    await this.requestJson<unknown>("POST", connectorAccountDisconnectPath(connectorAccountId));
  }

  async listMailboxMessages(query: ListMailboxMessagesQuery): Promise<MailboxMessageListResponse> {
    const params = new URLSearchParams();
    params.set("page_size", String(query.pageSize ?? MAILBOX_UI_PAGE_SIZE));
    if (query.cursor) {
      params.set("cursor", query.cursor);
    }
    return this.requestJson<MailboxMessageListResponse>(
      "GET",
      `${connectorAccountMessagesPath(query.connectorAccountId)}?${params.toString()}`,
    );
  }

  async analyzeMailboxMessage(
    query: AnalyzeMailboxMessageQuery,
  ): Promise<CommunicationAnalysisResponse> {
    return this.requestJson<CommunicationAnalysisResponse>(
      "POST",
      connectorAccountMessageAnalyzePath(query.connectorAccountId),
      { provider_message_id: query.providerMessageId },
    );
  }

  async listMailboxAttachments(
    query: ListMailboxAttachmentsQuery,
  ): Promise<AttachmentMetadataListResponse> {
    const params = new URLSearchParams();
    params.set("provider_message_id", query.providerMessageId);
    return this.requestJson<AttachmentMetadataListResponse>(
      "GET",
      `${connectorAccountAttachmentsPath(query.connectorAccountId)}?${params.toString()}`,
    );
  }

  async analyzeMailboxAttachment(
    query: AnalyzeMailboxAttachmentQuery,
  ): Promise<AttachmentAnalysisResponse> {
    return this.requestJson<AttachmentAnalysisResponse>(
      "POST",
      connectorAccountAttachmentAnalyzePath(query.connectorAccountId),
      {
        provider_message_id: query.providerMessageId,
        provider_attachment_id: query.providerAttachmentId,
      },
    );
  }

  async listAttachmentAnalyses(
    query: ListAttachmentAnalysesQuery = {},
  ): Promise<AttachmentAnalysisListResponse> {
    const params = new URLSearchParams();
    params.set("limit", String(query.limit ?? 20));
    params.set("offset", String(query.offset ?? 0));
    if (query.connectorAccountId) {
      params.set("connector_account_id", query.connectorAccountId);
    }
    if (query.providerMessageId) {
      params.set("provider_message_id", query.providerMessageId);
    }
    return this.requestJson<AttachmentAnalysisListResponse>(
      "GET",
      `${ATTACHMENT_ANALYSES_PATH}?${params.toString()}`,
    );
  }

  async getAttachmentAnalysis(attachmentAnalysisId: string): Promise<AttachmentAnalysisResponse> {
    return this.requestJson<AttachmentAnalysisResponse>(
      "GET",
      attachmentAnalysisPath(attachmentAnalysisId),
    );
  }

  async createWorkflowAction(query: CreateWorkflowActionQuery): Promise<WorkflowActionResponse> {
    return this.requestJson<WorkflowActionResponse>("POST", WORKFLOW_ACTIONS_PATH, {
      analysis_id: query.analysisId,
    });
  }

  async getWorkflowAction(actionId: string): Promise<WorkflowActionResponse> {
    return this.requestJson<WorkflowActionResponse>("GET", workflowActionPath(actionId));
  }

  async approveWorkflowAction(actionId: string): Promise<WorkflowActionResponse> {
    return this.requestJson<WorkflowActionResponse>("POST", workflowActionApprovePath(actionId));
  }

  async rejectWorkflowAction(actionId: string): Promise<WorkflowActionResponse> {
    return this.requestJson<WorkflowActionResponse>("POST", workflowActionRejectPath(actionId));
  }

  async executeWorkflowAction(actionId: string): Promise<WorkflowActionResponse> {
    return this.requestJson<WorkflowActionResponse>("POST", workflowActionExecutePath(actionId));
  }

  private async requestJson<T>(method: string, path: string, body?: unknown): Promise<T> {
    let token: string;
    try {
      token = await this.tokenProvider.acquireAccessToken();
    } catch (error) {
      if (error instanceof InteractionRequiredError) {
        throw new EciApiError(401, "interaction_required", messageForKind("interaction_required"));
      }
      throw error;
    }

    const headers: Record<string, string> = {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "X-Request-ID": this.createRequestId(),
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const response = await this.fetchImpl(new URL(path, `${this.baseUrl}/`).toString(), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      const kind = kindForStatus(response.status);
      throw new EciApiError(
        response.status,
        kind,
        messageForKind(kind),
        await readAttachmentDetailClass(response),
      );
    }

    return (await response.json()) as T;
  }
}

async function readAttachmentDetailClass(response: Response) {
  try {
    const body: unknown = await response.clone().json();
    if (typeof body !== "object" || body === null || !("detail" in body)) {
      return null;
    }
    const payload = body as { detail: unknown; code?: unknown };
    return classifyAttachmentDetail(payload.detail, payload.code);
  } catch {
    return null;
  }
}
