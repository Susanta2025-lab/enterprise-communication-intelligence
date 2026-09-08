import { describe, expect, it } from "vitest";

import {
  friendlyAttachmentType,
  isImageAttachmentType,
  isOversizedReportedSize,
  isSupportedAttachmentType,
} from "../lib/attachmentType";

describe("attachment type helpers", () => {
  it("classifies supported types from MIME or extension", () => {
    expect(friendlyAttachmentType("Contract.pdf", "application/pdf")).toBe("PDF");
    expect(friendlyAttachmentType("notes.DOCX", "application/octet-stream")).toBe("DOCX");
    expect(friendlyAttachmentType("readme.txt", "text/plain")).toBe("TXT");
    expect(friendlyAttachmentType("scan.jpg", "image/jpeg")).toBe("JPEG");
    expect(friendlyAttachmentType("diagram.png", "image/png")).toBe("PNG");
    expect(friendlyAttachmentType("payload.zip", "application/zip")).toBe("Other");
  });

  it("identifies JPEG/PNG for image-capability UX gating", () => {
    expect(isImageAttachmentType("scan.jpg", "image/jpeg")).toBe(true);
    expect(isImageAttachmentType("diagram.png", "image/png")).toBe(true);
    expect(isImageAttachmentType("Contract.pdf", "application/pdf")).toBe(false);
  });

  it("treats frontend type checks as display-only, not security", () => {
    expect(isSupportedAttachmentType("Contract.pdf", "application/pdf")).toBe(true);
    expect(isSupportedAttachmentType("payload.zip", "application/zip")).toBe(false);
    expect(isOversizedReportedSize(5 * 1024 * 1024)).toBe(false);
    expect(isOversizedReportedSize(5 * 1024 * 1024 + 1)).toBe(true);
  });
});
