import { useNavigate } from "react-router-dom";

import type { ConnectorAccount } from "../../api/connectorAccounts";
import { mailboxWorkspacePath } from "../../navigation/paths";
import { Button } from "../ui/button";
import { AccountIdentity } from "./AccountIdentity";
import { CapabilityBadge } from "./CapabilityBadge";
import { ConnectorStatus } from "./ConnectorStatus";
import { providerLabel, RECONNECT_SAME_ACCOUNT_LABEL } from "./copy";
import { PermissionGate } from "./PermissionGate";

type ConnectorCardProps = {
  account: ConnectorAccount;
  connectBusy: boolean;
  onReconnect: (account: ConnectorAccount) => void;
  onDisconnect: (account: ConnectorAccount) => void;
};

export function ConnectorCard({
  account,
  connectBusy,
  onReconnect,
  onDisconnect,
}: ConnectorCardProps) {
  const navigate = useNavigate();
  const label = providerLabel(account.provider);
  const capabilities = account.granted_capabilities ?? [];
  const canOpenMailbox = account.status === "active";
  const canReconnect = account.status === "reauth_required" || account.status === "disconnected";
  const canDisconnect = account.status === "active" || account.status === "reauth_required";

  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="min-w-0">
        <h3 className="text-base font-semibold break-words text-slate-900">{label}</h3>
        <AccountIdentity account={account} />
        <div className="mt-3">
          <ConnectorStatus status={account.status} />
        </div>
      </div>
      {capabilities.length > 0 ? (
        <ul className="flex flex-wrap gap-2" aria-label={`${label} capabilities`}>
          {capabilities.map((capability) => (
            <li key={capability}>
              <CapabilityBadge capability={capability} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">No mailbox capabilities currently granted.</p>
      )}
      <div className="mt-auto flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {canOpenMailbox ? (
          <Button className="w-full sm:w-auto" onClick={() => navigate(mailboxWorkspacePath(account.id))}>
            Open mailbox
          </Button>
        ) : null}
        <PermissionGate
          permission="communications:connect"
          fallback={
            <p className="text-sm text-slate-600">
              Connecting or disconnecting a mailbox requires the communications:connect permission.
            </p>
          }
        >
          <>
            {canReconnect ? (
              <Button
                className="w-full sm:w-auto"
                onClick={() => onReconnect(account)}
                disabled={connectBusy}
              >
                {RECONNECT_SAME_ACCOUNT_LABEL}
              </Button>
            ) : null}
            {canDisconnect ? (
              <Button
                className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
                onClick={() => onDisconnect(account)}
                disabled={connectBusy}
              >
                Disconnect
              </Button>
            ) : null}
          </>
        </PermissionGate>
      </div>
    </article>
  );
}
