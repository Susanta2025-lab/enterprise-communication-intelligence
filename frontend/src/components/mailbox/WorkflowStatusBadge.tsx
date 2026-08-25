import { workflowStatusLabel } from "./copy";

type WorkflowStatusBadgeProps = {
  status: string;
};

export function WorkflowStatusBadge({ status }: WorkflowStatusBadgeProps) {
  const terminal = status === "executed" || status === "rejected" || status === "failed";
  return (
    <p className="text-sm" role={terminal ? "status" : undefined}>
      <span className="font-medium text-slate-500">Status: </span>
      <span className="font-semibold text-slate-900">{workflowStatusLabel(status)}</span>
    </p>
  );
}
