export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function emptyAttachmentMetadata() {
  return { items: [] as const, truncated: false };
}

export function emptyAttachmentHistory() {
  return { items: [] as const, limit: 20, offset: 0 };
}

export function isAttachmentAnalyzeUrl(url: string): boolean {
  return url.includes("/attachments/analyze");
}

export function isAttachmentMetadataUrl(url: string): boolean {
  return url.includes("/attachments") && !url.includes("/attachments/analyze");
}

export function isAttachmentHistoryUrl(url: string): boolean {
  return url.includes("/attachment-analyses");
}

export function isMailboxAnalyzeUrl(url: string): boolean {
  return url.includes("/messages/analyze") && !url.includes("/attachments");
}

export function isMailboxListUrl(url: string): boolean {
  return url.includes("/messages") && !url.includes("/analyze") && !url.includes("/attachments");
}

export function attachmentAnalyzeCalls(fetchImpl: { mock: { calls: readonly unknown[][] } }) {
  return fetchImpl.mock.calls.filter(([url]) => isAttachmentAnalyzeUrl(String(url)));
}

export function attachmentMetadataCalls(fetchImpl: { mock: { calls: readonly unknown[][] } }) {
  return fetchImpl.mock.calls.filter(([url]) => isAttachmentMetadataUrl(String(url)));
}

export function mailboxAnalyzeCalls(fetchImpl: { mock: { calls: readonly unknown[][] } }) {
  return fetchImpl.mock.calls.filter(([url]) => isMailboxAnalyzeUrl(String(url)));
}
