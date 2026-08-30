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
  /** Optional safe mailbox identity from a future backend contract. Never an internal locator. */
  display_identity?: string | null;
};

export const ACCOUNT_IDENTITY_UNAVAILABLE = "Account identity unavailable";

export const CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON =
  "account_selection_not_available" as const;

export type ConnectAnotherAccountAvailability = {
  supported: false;
  reason: typeof CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON;
};

export type ConnectAnotherAccountRequest = {
  provider: ConnectorProvider;
  intent: "connect_another_account";
};

export class ConnectAnotherAccountUnavailableError extends Error {
  readonly reason = CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON;

  constructor() {
    super(
      "Connecting a different account is not available until the backend can guarantee account selection.",
    );
    this.name = "ConnectAnotherAccountUnavailableError";
  }
}

export function connectorDisplayIdentity(
  account: Pick<ConnectorAccount, "display_identity">,
): string {
  const value = account.display_identity;
  if (typeof value === "string" && value.trim() !== "") {
    return value.trim();
  }
  return ACCOUNT_IDENTITY_UNAVAILABLE;
}

export function connectAnotherAccountAvailability(
  provider: ConnectorProvider,
): ConnectAnotherAccountAvailability {
  void provider;
  return {
    supported: false,
    reason: CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON,
  };
}

/**
 * Future call site for connecting a different mailbox account.
 * Must not start the current first-connect or exact-account reauthorize OAuth flows.
 */
export function startConnectAnotherAccount(request: ConnectAnotherAccountRequest): never {
  void request;
  throw new ConnectAnotherAccountUnavailableError();
}

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
