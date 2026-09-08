import { ConnectorLogo } from "./ConnectorLogo";

type ProviderIconProps = {
  provider: string;
  className?: string;
};

/** @deprecated Prefer ConnectorLogo. Kept as a thin alias for existing imports. */
export function ProviderIcon({ provider, className }: ProviderIconProps) {
  return <ConnectorLogo provider={provider} className={className} decorative />;
}
