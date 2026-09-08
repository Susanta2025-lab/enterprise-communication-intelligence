import { useEffect, useId, useRef } from "react";

import type { AttachmentAnalysisResponse, AttachmentMetadataItem } from "../../api/attachments";
import { presentProductError } from "../../errors/presentProductError";
import { formatReportedSize } from "../../lib/formatBytes";
import {
  friendlyAttachmentType,
  isImageAttachmentType,
  isOversizedReportedSize,
  isSupportedAttachmentType,
} from "../../lib/attachmentType";
import { ProductErrorState } from "../feedback/ProductErrorState";
import { Button } from "../ui/button";
import { AttachmentAnalysisPanel } from "./AttachmentAnalysisPanel";
import { AttachmentTypeIcon } from "./AttachmentTypeIcon";
import {
  ANALYZE_ATTACHMENT_LABEL,
  ANALYZING_ATTACHMENT_COPY,
  COMPLETED_STATUS,
  IMAGE_ANALYSIS_UNAVAILABLE_STATUS,
  INLINE_STATUS,
  NOT_ANALYZED_STATUS,
  PREVIOUS_ANALYSES_HEADING,
  TOO_LARGE_STATUS,
  UNSUPPORTED_STATUS,
  displayAttachmentFilename,
} from "./attachmentCopy";
import { formatMailboxTimestamp } from "../../lib/formatTimestamp";

type AttachmentItemProps = {
  item: AttachmentMetadataItem;
  canAnalyze: boolean;
  imageAnalysisAvailable: boolean;
  pending: boolean;
  result: AttachmentAnalysisResponse | null;
  history: readonly AttachmentAnalysisResponse[];
  error: unknown;
  onAnalyze: () => void;
};

export function AttachmentItem({
  item,
  canAnalyze,
  imageAnalysisAvailable,
  pending,
  result,
  history,
  error,
  onAnalyze,
}: AttachmentItemProps) {
  const labelId = useId();
  const errorRef = useRef<HTMLDivElement>(null);
  const filename = displayAttachmentFilename(item.filename);
  const type = friendlyAttachmentType(item.filename, item.media_type);
  const supported = isSupportedAttachmentType(item.filename, item.media_type);
  const imageType = isImageAttachmentType(item.filename, item.media_type);
  const imageUnavailable = imageType && !imageAnalysisAvailable;
  const oversized = isOversizedReportedSize(item.reported_size);
  const offerAnalyze = canAnalyze && supported && !oversized && !imageUnavailable;
  const canRequestAnalyze = offerAnalyze && !pending;
  const latest = result ?? history[0] ?? null;
  const previous = latest
    ? history.filter((entry) => entry.attachment_analysis_id !== latest.attachment_analysis_id)
    : history;
  const status = pending
    ? ANALYZING_ATTACHMENT_COPY
    : latest
      ? COMPLETED_STATUS
      : oversized
        ? TOO_LARGE_STATUS
        : imageUnavailable
          ? IMAGE_ANALYSIS_UNAVAILABLE_STATUS
          : supported
            ? NOT_ANALYZED_STATUS
            : UNSUPPORTED_STATUS;
  const errorView = error ? presentProductError("attachment_analyze", error) : null;

  useEffect(() => {
    if (error) {
      errorRef.current?.focus();
    }
  }, [error]);

  const metaParts = [`${type} · ${formatReportedSize(item.reported_size)}`];
  if (item.is_inline) {
    metaParts.push(INLINE_STATUS);
  }

  return (
    <li className="min-w-0 rounded-md border border-slate-200 p-4">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start">
        <AttachmentTypeIcon filename={item.filename} mediaType={item.media_type} />
        <div className="min-w-0 flex-1">
          <p id={labelId} className="min-w-0 break-words font-medium text-slate-900">
            {filename}
          </p>
          <p className="mt-1 text-sm text-slate-600">{metaParts.join(" · ")}</p>
          <p
            className="mt-1 text-sm text-slate-700"
            data-testid="attachment-status"
            role={pending ? "status" : undefined}
          >
            {status}
          </p>
          {offerAnalyze ? (
            <div className="mt-3">
              <Button
                className="w-full sm:w-auto"
                onClick={onAnalyze}
                disabled={!canRequestAnalyze}
                aria-busy={pending}
                aria-describedby={labelId}
                aria-label={`${ANALYZE_ATTACHMENT_LABEL}: ${filename}`}
              >
                {ANALYZE_ATTACHMENT_LABEL}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
      {errorView ? (
        <div className="mt-4">
          <ProductErrorState
            ref={errorRef}
            {...errorView}
            onRetry={errorView.retryLabel ? onAnalyze : undefined}
          />
        </div>
      ) : null}
      {latest ? (
        <div className="mt-4">
          <AttachmentAnalysisPanel
            result={latest}
            headingId={`attachment-analysis-${item.provider_attachment_id}`}
          />
        </div>
      ) : null}
      {previous.length > 0 ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-800">
            {PREVIOUS_ANALYSES_HEADING}
          </summary>
          <ol className="mt-3 space-y-3">
            {previous.map((entry) => (
              <li key={entry.attachment_analysis_id} className="min-w-0">
                <p className="mb-2 text-sm text-slate-600">
                  {formatMailboxTimestamp(entry.created_at) ?? "Previous analysis"}
                </p>
                <AttachmentAnalysisPanel
                  result={entry}
                  headingId={`previous-attachment-analysis-${entry.attachment_analysis_id}`}
                />
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </li>
  );
}
