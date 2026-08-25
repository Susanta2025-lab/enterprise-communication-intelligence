export const DASHBOARD_PATH = "/";

export function mailboxWorkspacePath(connectorAccountId: string): string {
  return `/mailbox/${connectorAccountId}`;
}
