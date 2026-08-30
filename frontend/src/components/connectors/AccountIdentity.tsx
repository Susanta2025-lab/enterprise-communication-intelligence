import { connectorDisplayIdentity, type ConnectorAccount } from "../../api/connectorAccounts";

type AccountIdentityProps = {
  account: ConnectorAccount;
};

export function AccountIdentity({ account }: AccountIdentityProps) {
  return (
    <div className="mt-2" data-testid="connector-account-identity">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Account</p>
      <p className="mt-0.5 text-sm break-words text-slate-800">{connectorDisplayIdentity(account)}</p>
    </div>
  );
}
