import { MAX_ATTACHMENT_CONTENT_BYTES } from "../api/attachments";

export type FriendlyAttachmentType = "PDF" | "DOCX" | "TXT" | "JPEG" | "PNG" | "Other";

const SUPPORTED_TYPES = new Set<FriendlyAttachmentType>(["PDF", "DOCX", "TXT", "JPEG", "PNG"]);

export function extensionOf(filename: string): string {
  const trimmed = filename.trim();
  const separator = trimmed.lastIndexOf(".");
  if (separator <= 0 || separator === trimmed.length - 1) {
    return "";
  }
  return trimmed.slice(separator).toLowerCase();
}

export function friendlyAttachmentType(
  filename: string,
  mediaType: string,
): FriendlyAttachmentType {
  const media = mediaType.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  const extension = extensionOf(filename);
  if (media === "application/pdf" || extension === ".pdf") {
    return "PDF";
  }
  if (
    media === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    extension === ".docx"
  ) {
    return "DOCX";
  }
  if (media === "text/plain" || extension === ".txt") {
    return "TXT";
  }
  if (media === "image/jpeg" || extension === ".jpg" || extension === ".jpeg") {
    return "JPEG";
  }
  if (media === "image/png" || extension === ".png") {
    return "PNG";
  }
  return "Other";
}

export function isSupportedAttachmentType(filename: string, mediaType: string): boolean {
  return SUPPORTED_TYPES.has(friendlyAttachmentType(filename, mediaType));
}

export function isOversizedReportedSize(reportedSize: number): boolean {
  return Number.isFinite(reportedSize) && reportedSize > MAX_ATTACHMENT_CONTENT_BYTES;
}
