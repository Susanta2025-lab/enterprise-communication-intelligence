import type { AccountInfo } from "@azure/msal-browser";

const PLACEHOLDER_NAMES = new Set(["unknown"]);

function usableDisplayLabel(value: string | undefined | null): string | null {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) {
    return null;
  }
  if (PLACEHOLDER_NAMES.has(trimmed.toLowerCase())) {
    return null;
  }
  return trimmed;
}

export function resolveDisplayName(account: AccountInfo | null): string | null {
  if (account === null) {
    return null;
  }
  return usableDisplayLabel(account.name) ?? usableDisplayLabel(account.username);
}
