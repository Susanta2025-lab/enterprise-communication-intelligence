import { cn } from "../../lib/utils";
import { statusDescription, statusLabel } from "./copy";

type ConnectorStatusProps = {
  status: string;
};

export function ConnectorStatus({ status }: ConnectorStatusProps) {
  const label = statusLabel(status);
  const description = statusDescription(status);
  return (
    <div>
      <p
        className={cn(
          "text-sm font-medium",
          status === "active" && "text-emerald-800",
          status === "reauth_required" && "text-amber-800",
          status === "disconnected" && "text-slate-700",
        )}
        data-testid="connector-status"
      >
        <span className="sr-only">Connection status: </span>
        {label}
      </p>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
    </div>
  );
}
