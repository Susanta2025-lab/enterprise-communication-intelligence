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
  EciApiError,
  GMAIL_AUTHORIZE_PATH,
  MICROSOFT_GRAPH_AUTHORIZE_PATH,
  kindForStatus,
  messageForKind,
  PROTECTED_ANALYSES_SMOKE_PATH,
  type AnalysisListResponse,
} from "./errors";

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
      throw new EciApiError(response.status, kind, messageForKind(kind));
    }

    return (await response.json()) as T;
  }
}
