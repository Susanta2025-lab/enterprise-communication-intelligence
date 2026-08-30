export const RECONNECT_SAME_ACCOUNT_LABEL = "Reconnect same account";
export const CONNECT_ANOTHER_GMAIL_LABEL = "Connect another Gmail account";
export const CONNECT_ANOTHER_OUTLOOK_LABEL = "Connect another Outlook account";
export const CONNECT_ANOTHER_UNAVAILABLE_COPY =
  "Connecting a different account is not available yet. The current authorization flow cannot guarantee a different mailbox and must not be used for this action.";

export function providerLabel(provider: string): string {
  if (provider === "gmail") {
    return "Gmail";
  }
  if (provider === "microsoft_graph") {
    return "Microsoft Outlook";
  }
  return "Mailbox";
}

export function connectAnotherAccountActionLabel(provider: string): string {
  if (provider === "gmail") {
    return CONNECT_ANOTHER_GMAIL_LABEL;
  }
  if (provider === "microsoft_graph") {
    return CONNECT_ANOTHER_OUTLOOK_LABEL;
  }
  return "Connect another account";
}

export function statusLabel(status: string): string {
  if (status === "active") {
    return "Active — mailbox available";
  }
  if (status === "reauth_required") {
    return "Reauthorization required";
  }
  if (status === "disconnected") {
    return "Disconnected";
  }
  return "Unknown status";
}

export function statusDescription(status: string): string {
  if (status === "active") {
    return "This mailbox is connected. Open it to browse recent messages.";
  }
  if (status === "reauth_required") {
    return "Mailbox authorization must be renewed. The mailbox was not deleted.";
  }
  if (status === "disconnected") {
    return "ECI no longer has active mailbox authorization for this mailbox account. Reconnect same account restores this same mailbox.";
  }
  return "Mailbox connection status could not be classified.";
}

export function capabilityLabel(capability: string): string {
  if (capability === "mail.read") {
    return "mail.read";
  }
  if (capability === "mail.send") {
    return "mail.send";
  }
  return capability;
}
