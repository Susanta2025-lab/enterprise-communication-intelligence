import type { AttachmentAnalysisResponse, AttachmentMetadataItem } from "../../api/attachments";
import { presentProductError } from "../../errors/presentProductError";
import { ProductErrorState } from "../feedback/ProductErrorState";
import { AttachmentItem } from "./AttachmentItem";
import {
  ATTACHMENT_ANALYZE_PERMISSION_HINT,
  ATTACHMENT_METADATA_LOADING_COPY,
  ATTACHMENT_PRIVACY_COPY,
  ATTACHMENT_TRUNCATED_LIST_COPY,
  ATTACHMENTS_HEADING,
  NO_ATTACHMENTS_COPY,
} from "./attachmentCopy";

type AttachmentsSectionProps = {
  canAnalyze: boolean;
  loading: boolean;
  listError: unknown;
  onRetryList: () => void;
  items: readonly AttachmentMetadataItem[];
  truncated: boolean;
  pendingId: string | null;
  resultFor: (providerAttachmentId: string) => AttachmentAnalysisResponse | null;
  errorFor: (providerAttachmentId: string) => unknown;
  historyFor: (providerAttachmentId: string) => readonly AttachmentAnalysisResponse[];
  onAnalyze: (providerAttachmentId: string) => void;
};

export function AttachmentsSection({
  canAnalyze,
  loading,
  listError,
  onRetryList,
  items,
  truncated,
  pendingId,
  resultFor,
  errorFor,
  historyFor,
  onAnalyze,
}: AttachmentsSectionProps) {
  const listErrorView = listError ? presentProductError("attachment_list", listError) : null;

  return (
    <section className="mt-6 min-w-0 space-y-4 border-t border-slate-200 pt-5" aria-labelledby="attachments-heading">
      <div className="min-w-0">
        <h4 id="attachments-heading" className="text-base font-semibold text-slate-900">
          {ATTACHMENTS_HEADING}
        </h4>
        <p className="mt-2 text-sm text-slate-600">{ATTACHMENT_PRIVACY_COPY}</p>
        {!canAnalyze ? (
          <p className="mt-2 text-sm text-slate-600">{ATTACHMENT_ANALYZE_PERMISSION_HINT}</p>
        ) : null}
      </div>
      {loading ? (
        <p role="status" className="text-sm text-slate-600" data-testid="attachments-loading">
          {ATTACHMENT_METADATA_LOADING_COPY}
        </p>
      ) : null}
      {listErrorView ? (
        <ProductErrorState
          {...listErrorView}
          onRetry={listErrorView.retryLabel ? onRetryList : undefined}
        />
      ) : null}
      {!loading && !listError && items.length === 0 ? (
        <p className="text-sm text-slate-600" data-testid="attachments-empty">
          {NO_ATTACHMENTS_COPY}
        </p>
      ) : null}
      {items.length > 0 ? (
        <ul className="space-y-3" aria-label={ATTACHMENTS_HEADING}>
          {items.map((item) => (
            <AttachmentItem
              key={item.provider_attachment_id}
              item={item}
              canAnalyze={canAnalyze}
              pending={pendingId === item.provider_attachment_id}
              result={resultFor(item.provider_attachment_id)}
              history={historyFor(item.provider_attachment_id)}
              error={errorFor(item.provider_attachment_id)}
              onAnalyze={() => onAnalyze(item.provider_attachment_id)}
            />
          ))}
        </ul>
      ) : null}
      {truncated ? (
        <p className="text-sm text-slate-600">{ATTACHMENT_TRUNCATED_LIST_COPY}</p>
      ) : null}
    </section>
  );
}
