import { MAX_ATTACHMENT_CONTENT_BYTES } from "../api/attachments";

export type FriendlyAttachmentType = "PDF" | "DOCX" | "TXT" | "XLSX" | "JPEG" | "PNG" | "Other";

const SUPPORTED_TYPES = new Set<FriendlyAttachmentType>(["PDF", "DOCX", "TXT", "XLSX", "JPEG", "PNG"]);
const UNSUPPORTED_SPREADSHEET_EXTENSIONS = new Set([".xls", ".xlsm", ".xlsb", ".csv", ".tsv"]);
const UNSUPPORTED_SPREADSHEET_MEDIA_TYPES = new Set([
  "application/vnd.ms-excel",
  "application/vnd.ms-excel.sheet.macroenabled.12",
  "application/vnd.ms-excel.sheet.binary.macroenabled.12",
  "text/csv",
  "application/csv",
  "text/tab-separated-values",
]);

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
  if (UNSUPPORTED_SPREADSHEET_EXTENSIONS.has(extension) || UNSUPPORTED_SPREADSHEET_MEDIA_TYPES.has(media)) {
    return "Other";
  }
  if (extension === ".xlsx" || media === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
    return "XLSX";
  }
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

export function isImageAttachmentType(filename: string, mediaType: string): boolean {
  const type = friendlyAttachmentType(filename, mediaType);
  return type === "JPEG" || type === "PNG";
}

export function isOversizedReportedSize(reportedSize: number): boolean {
  return Number.isFinite(reportedSize) && reportedSize > MAX_ATTACHMENT_CONTENT_BYTES;
}
