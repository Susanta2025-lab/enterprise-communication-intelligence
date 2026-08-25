import { useEffect, useRef } from "react";

import { EciApiError } from "../../api/errors";
import type { CommunicationAnalysisResponse } from "../../api/mailbox";
import { AnalysisErrorState } from "./AnalysisErrorState";
import { AnalysisLoadingSkeleton } from "./AnalysisLoadingSkeleton";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalyzeButton } from "./AnalyzeButton";
import { analyzeErrorMessage, analyzeRetryLabel } from "./copy";

type MessageAnalysisSectionProps = {
  canAnalyze: boolean;
  pending: boolean;
  result: CommunicationAnalysisResponse | null;
  error: unknown;
  onAnalyze: () => void;
  onRetry: () => void;
};

export function MessageAnalysisSection({
  canAnalyze,
  pending,
  result,
  error,
  onAnalyze,
  onRetry,
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

  const retryLabel = error ? analyzeRetryLabel(error) : null;
  const showDashboardLink =
    error instanceof EciApiError && (error.status === 404 || error.status === 409);
  const showInitialSkeleton = pending && !result;
  const showReanalyzeStatus = pending && Boolean(result);

  return (
    <div className="mt-6 space-y-4 border-t border-slate-200 pt-5">
      <AnalyzeButton
        canAnalyze={canAnalyze}
        hasResult={Boolean(result)}
        pending={pending}
        onAnalyze={onAnalyze}
      />
      {showInitialSkeleton ? <AnalysisLoadingSkeleton /> : null}
      {showReanalyzeStatus ? <AnalysisLoadingSkeleton reanalyzing /> : null}
      {error ? (
        <AnalysisErrorState
          ref={errorRef}
          message={analyzeErrorMessage(error)}
          onRetry={retryLabel ? onRetry : undefined}
          retryLabel={retryLabel ?? undefined}
          showDashboardLink={showDashboardLink}
        />
      ) : null}
      {result ? <AnalysisPanel ref={resultRef} result={result} /> : null}
    </div>
  );
}
