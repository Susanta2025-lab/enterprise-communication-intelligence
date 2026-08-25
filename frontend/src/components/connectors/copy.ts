export function providerLabel(provider: string): string {
  if (provider === "gmail") {
    return "Gmail";
  }
  if (provider === "microsoft_graph") {
    return "Microsoft Outlook";
  }
  return "Mailbox";
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
    return "This mailbox is connected. Mailbox message access will be available in a later release.";
  }
  if (status === "reauth_required") {
    return "Mailbox authorization must be renewed. The mailbox was not deleted.";
  }
  if (status === "disconnected") {
    return "ECI no longer has active mailbox authorization for this connection. You can reconnect later.";
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
