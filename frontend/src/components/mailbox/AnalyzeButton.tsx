import { Button } from "../ui/button";
import {
  ANALYZE_ACTION_LABEL,
  ANALYZE_PERMISSION_HINT,
  REANALYZE_ACTION_LABEL,
} from "./copy";

type AnalyzeButtonProps = {
  canAnalyze: boolean;
  hasResult: boolean;
  pending: boolean;
  onAnalyze: () => void;
};

export function AnalyzeButton({
  canAnalyze,
  hasResult,
  pending,
  onAnalyze,
}: AnalyzeButtonProps) {
  const label = hasResult ? REANALYZE_ACTION_LABEL : ANALYZE_ACTION_LABEL;
  const describedBy = canAnalyze ? undefined : "analyze-permission-hint";

  return (
    <div>
      <Button
        onClick={onAnalyze}
        disabled={!canAnalyze || pending}
        aria-busy={pending}
        aria-describedby={describedBy}
      >
        {label}
      </Button>
      {canAnalyze ? null : (
        <p id="analyze-permission-hint" className="mt-2 text-sm text-slate-600">
          {ANALYZE_PERMISSION_HINT}
        </p>
      )}
    </div>
  );
}
