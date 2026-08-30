import { useId } from "react";

import {
  connectAnotherAccountAvailability,
  type ConnectorProvider,
} from "../../api/connectorAccounts";
import { Button } from "../ui/button";
import { CONNECT_ANOTHER_UNAVAILABLE_COPY, connectAnotherAccountActionLabel } from "./copy";

type ConnectAnotherAccountProps = {
  provider: ConnectorProvider;
};

export function ConnectAnotherAccount({ provider }: ConnectAnotherAccountProps) {
  const descriptionId = useId();
  const availability = connectAnotherAccountAvailability(provider);
  const label = connectAnotherAccountActionLabel(provider);

  return (
    <aside
      className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
      data-testid={`connect-another-${provider}`}
    >
      <Button
        className="w-full sm:w-auto"
        disabled={!availability.supported}
        aria-describedby={descriptionId}
      >
        {label}
      </Button>
      <p id={descriptionId} className="mt-2 text-sm text-slate-600">
        {CONNECT_ANOTHER_UNAVAILABLE_COPY}
      </p>
    </aside>
  );
}
