import type { EciApiClient } from "../../api/client";
import { CandidatePanel } from "../workItems/CandidatePanel";
import { useEffect, useRef, type ReactNode } from "react";

import type { CommunicationAnalysisResponse } from "../../api/mailbox";
import { ProductErrorState } from "../feedback/ProductErrorState";
import { presentProductError } from "../../errors/presentProductError";
import { AnalysisLoadingSkeleton } from "./AnalysisLoadingSkeleton";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalyzeButton } from "./AnalyzeButton";

type MessageAnalysisSectionProps = {
  apiClient?: EciApiClient;
  canAnalyze: boolean;
  pending: boolean;
  result: CommunicationAnalysisResponse | null;
  error: unknown;
  onAnalyze: () => void;
  onRetry: () => void;
  workflow?: ReactNode;
};

export function MessageAnalysisSection({
  apiClient,
  canAnalyze,
  pending,
  result,
  error,
  onAnalyze,
  onRetry,
  workflow,
}: MessageAnalysisSectionProps) {
  const errorRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLElement>(null);
  const hadResult = useRef(false);

  useEffect(() => {
    if (error) {
      errorRef.current?.focus();
    }
  }, [error]);

  useEffect(() => {
    if (result && !hadResult.current && !pending) {
      resultRef.current?.focus();
    }
    hadResult.current = Boolean(result);
  }, [result, pending]);

  const errorView = error ? presentProductError("analyze", error) : null;
  const showInitialSkeleton = pending && !result;
  const showReanalyzeStatus = pending && Boolean(result);

  return (
    <div className="mt-6 min-w-0 space-y-4 border-t border-slate-200 pt-5">
      <AnalyzeButton
        canAnalyze={canAnalyze}
        hasResult={Boolean(result)}
        pending={pending}
        onAnalyze={onAnalyze}
      />
      {showInitialSkeleton ? <AnalysisLoadingSkeleton /> : null}
      {showReanalyzeStatus ? <AnalysisLoadingSkeleton reanalyzing /> : null}
      {errorView ? (
        <ProductErrorState
          ref={errorRef}
          {...errorView}
          onRetry={errorView.retryLabel ? onRetry : undefined}
        />
      ) : null}
      {result ? <AnalysisPanel ref={resultRef} result={result} /> : null}
      {result?.analysis_id && apiClient && <CandidatePanel api={apiClient} source={{ source_kind: "communication_analysis", source_id: result.analysis_id }} />}
      {result ? workflow : null}
    </div>
  );
}
