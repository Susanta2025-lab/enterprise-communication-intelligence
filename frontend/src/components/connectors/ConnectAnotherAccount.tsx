import { useId } from "react";

import {
  connectAnotherAccountAvailability,
  type ConnectorProvider,
} from "../../api/connectorAccounts";
import { Button } from "../ui/button";
import {
  CONNECT_ANOTHER_AVAILABLE_COPY,
  CONNECT_ANOTHER_UNAVAILABLE_COPY,
  connectAnotherAccountActionLabel,
} from "./copy";

type ConnectAnotherAccountProps = {
  provider: ConnectorProvider;
  busy?: boolean;
  onConnect?: () => void;
};

export function ConnectAnotherAccount({
  provider,
  busy = false,
  onConnect,
}: ConnectAnotherAccountProps) {
  const descriptionId = useId();
  const availability = connectAnotherAccountAvailability(provider);
  const label = connectAnotherAccountActionLabel(provider);
  const enabled = availability.supported && onConnect !== undefined && !busy;

  return (
    <aside
      className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
      data-testid={`connect-another-${provider}`}
    >
      <Button
        className="w-full sm:w-auto"
        disabled={!enabled}
        aria-describedby={descriptionId}
        onClick={enabled ? onConnect : undefined}
      >
        {label}
      </Button>
      <p id={descriptionId} className="mt-2 text-sm text-slate-600">
        {availability.supported ? CONNECT_ANOTHER_AVAILABLE_COPY : CONNECT_ANOTHER_UNAVAILABLE_COPY}
      </p>
    </aside>
  );
}
