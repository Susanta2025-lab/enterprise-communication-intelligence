export const DASHBOARD_PATH = "/";
export const CONTEXTS_PATH = "/contexts";

export function mailboxWorkspacePath(connectorAccountId: string): string {
  return `/mailbox/${connectorAccountId}`;
}

export function contextWorkspacePath(contextId: string): string {
  return `/contexts/${contextId}`;
}
