export type ConnectorProvider = "gmail" | "microsoft_graph";

export type ConnectorAccountStatus = "active" | "disconnected" | "reauth_required";

export type CommunicationCapability = "mail.read" | "mail.send";

export type ConnectorAccount = {
  id: string;
  provider: string;
  status: string;
  granted_capabilities: readonly string[] | null;
  created_at: string;
  updated_at: string;
};

export type ConnectorAccountListResponse = {
  items: readonly ConnectorAccount[];
  limit: number;
  offset: number;
};

export type AuthorizationStartResponse = {
  authorization_url: string;
  expires_at: string;
};

export type ListConnectorAccountsQuery = {
  limit?: number;
  offset?: number;
};

export function connectorAccountReauthorizePath(connectorAccountId: string): string {
  return `/api/v1/connector-accounts/${connectorAccountId}/reauthorize`;
}

export function connectorAccountDisconnectPath(connectorAccountId: string): string {
  return `/api/v1/connector-accounts/${connectorAccountId}/disconnect`;
}
