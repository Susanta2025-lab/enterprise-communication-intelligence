import { providerLabel } from "./copy";

type ConnectorLogoProps = {
  provider: string;
  className?: string;
  /**
   * When true (default), logo is decorative beside visible provider text.
   * When false, logo is the sole identifier and receives an accessible name.
   */
  decorative?: boolean;
};

/**
 * Local Gmail / Outlook brand marks. Vendor colors are preserved.
 * Unknown providers fall back to a neutral mailbox glyph.
 */
export function ConnectorLogo({
  provider,
  className,
  decorative = true,
}: ConnectorLogoProps) {
  const label = `${providerLabel(provider)} logo`;
  const a11yProps = decorative
    ? { "aria-hidden": true as const, focusable: false as const }
    : { role: "img" as const, "aria-label": label };

  if (provider === "gmail") {
    return <GmailLogo className={className} dataProvider={provider} {...a11yProps} />;
  }
  if (provider === "microsoft_graph") {
    return <OutlookLogo className={className} dataProvider={provider} {...a11yProps} />;
  }
  return <GenericMailboxLogo className={className} dataProvider={provider} {...a11yProps} />;
}

type MarkProps = {
  className?: string;
  dataProvider: string;
  "aria-hidden"?: boolean;
  focusable?: boolean;
  role?: "img";
  "aria-label"?: string;
};

function GmailLogo({ className, dataProvider, ...a11y }: MarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      width="24"
      height="24"
      data-provider={dataProvider}
      data-connector-logo="gmail"
      {...a11y}
    >
      <path fill="#4CAF50" d="M45 16.2 40 18.95 35 23.7V40h7c1.66 0 3-1.34 3-3V16.2Z" />
      <path fill="#1E88E5" d="M3 16.2 6.61 17.91 13 23.7V40H6c-1.66 0-3-1.34-3-3V16.2Z" />
      <path fill="#E53935" d="M35 11.2 24 19.45 13 11.2 12 17l1 6.7 11 8.25L35 23.7 36 17l-1-5.8Z" />
      <path
        fill="#C62828"
        d="M3 12.3V16.2l10 7.5V11.2L9.88 8.86A3.28 3.28 0 0 0 7.3 8 4.3 4.3 0 0 0 3 12.3Z"
      />
      <path
        fill="#FBC02D"
        d="M45 12.3V16.2l-10 7.5V11.2l3.12-2.34A3.28 3.28 0 0 1 40.7 8 4.3 4.3 0 0 1 45 12.3Z"
      />
    </svg>
  );
}

function OutlookLogo({ className, dataProvider, ...a11y }: MarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      width="24"
      height="24"
      data-provider={dataProvider}
      data-connector-logo="outlook"
      {...a11y}
    >
      <path
        fill="#0A2767"
        d="M7 8h20a4 4 0 0 1 4 4v24a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V12a4 4 0 0 1 4-4Z"
      />
      <path fill="#0072C6" d="M27 12H7a4 4 0 0 0-4 4v16a4 4 0 0 0 4 4h20V12Z" />
      <path
        fill="#0072C6"
        d="M45 14.5v19c0 1.38-1.12 2.5-2.5 2.5H27V12h15.5c1.38 0 2.5 1.12 2.5 2.5Z"
      />
      <path
        fill="#28A8EA"
        d="M45 14.5c0-1.38-1.12-2.5-2.5-2.5H27v10.75L42.8 12.8A2.48 2.48 0 0 1 45 14.5Z"
      />
      <path fill="#50D9FF" fillOpacity={0.85} d="M27 22.75 42.8 12.8A2.48 2.48 0 0 1 45 14.5v14L27 22.75Z" />
      <path
        fill="#FFFFFF"
        d="M17 15.5c-4.14 0-7.5 3.13-7.5 7s3.36 7 7.5 7 7.5-3.13 7.5-7-3.36-7-7.5-7Zm0 3c2.35 0 4.25 1.79 4.25 4s-1.9 4-4.25 4-4.25-1.79-4.25-4 1.9-4 4.25-4Z"
      />
    </svg>
  );
}

function GenericMailboxLogo({ className, dataProvider, ...a11y }: MarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="24"
      height="24"
      data-provider={dataProvider}
      data-connector-logo="generic"
      {...a11y}
    >
      <rect width="24" height="24" rx="6" fill="#e2e8f0" />
      <path
        d="M5 8.5 12 13l7-4.5V16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8.5Z"
        fill="#0f172a"
      />
      <path d="M5.4 7.2 12 11.4l6.6-4.2H5.4Z" fill="#334155" />
    </svg>
  );
}
