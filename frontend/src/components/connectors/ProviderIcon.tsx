type ProviderIconProps = {
  provider: string;
  className?: string;
};

export function ProviderIcon({ provider, className }: ProviderIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="24"
      height="24"
      aria-hidden="true"
      focusable="false"
      data-provider={provider}
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
