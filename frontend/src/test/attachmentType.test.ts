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

describe("Phase 21E format policy", () => {
  it.each(["Budget.xlsx", "Budget.XLSX", " Budget.xlsx "])("recognizes %s", (filename) => {
    expect(friendlyAttachmentType(filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")).toBe("XLSX");
    expect(isSupportedAttachmentType(filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")).toBe(true);
  });

  it.each(["xls", "xlsm", "xlsb", "csv", "tsv"])("rejects .%s before MIME fallback", (extension) => {
    for (const media of ["text/plain", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"]) {
      expect(isSupportedAttachmentType(`Data.${extension.toUpperCase()}`, media)).toBe(false);
    }
  });

  it.each(["application/vnd.ms-excel", "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12", "text/csv", "text/tab-separated-values"])(
    "rejects unsupported spreadsheet MIME %s", (media) => {
      expect(isSupportedAttachmentType("data", media)).toBe(false);
      expect(isSupportedAttachmentType("data.txt", media)).toBe(false);
    },
  );
});
