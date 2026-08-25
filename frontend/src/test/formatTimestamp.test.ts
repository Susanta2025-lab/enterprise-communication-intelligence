import { describe, expect, it } from "vitest";

import { formatMailboxTimestamp } from "../lib/formatTimestamp";

describe("mailbox timestamp formatting", () => {
  it("formats an ISO timestamp in the browser locale", () => {
    const formatted = formatMailboxTimestamp("2026-08-25T15:30:00Z");
    expect(formatted).toBeTruthy();
    expect(formatted).not.toContain("2026-08-25T15:30:00Z");
  });

  it("returns null for missing or invalid values", () => {
    expect(formatMailboxTimestamp(null)).toBeNull();
    expect(formatMailboxTimestamp(undefined)).toBeNull();
    expect(formatMailboxTimestamp("")).toBeNull();
    expect(formatMailboxTimestamp("not-a-date")).toBeNull();
  });
});
