type OAuthReturnNoticeProps = {
  tone: "success" | "error";
  text: string;
};

export function OAuthReturnNotice({ tone, text }: OAuthReturnNoticeProps) {
  const role = tone === "error" ? "alert" : "status";
  const className =
    tone === "error"
      ? "rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
      : "rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900";
  return (
    <div role={role} aria-live="polite" className={className} data-testid="oauth-return-notice">
      {text}
    </div>
  );
}
