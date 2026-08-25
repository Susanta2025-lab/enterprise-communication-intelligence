import { cn } from "../../lib/utils";
import { priorityLabel } from "./copy";

type PriorityBadgeProps = {
  level: string | null | undefined;
  rationale?: string | null;
};

const LEVEL_TONE: Record<string, string> = {
  low: "bg-slate-100 text-slate-800",
  medium: "bg-sky-100 text-sky-900",
  high: "bg-amber-100 text-amber-900",
  critical: "bg-red-100 text-red-900",
};

export function PriorityBadge({ level, rationale }: PriorityBadgeProps) {
  const label = priorityLabel(level);
  const tone = (level && LEVEL_TONE[level]) || "bg-slate-100 text-slate-800";

  return (
    <div>
      <p>
        <span className="sr-only">Priority: </span>
        <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium", tone)}>
          {label}
        </span>
      </p>
      {rationale ? <p className="mt-1 text-sm text-slate-600">{rationale}</p> : null}
    </div>
  );
}
