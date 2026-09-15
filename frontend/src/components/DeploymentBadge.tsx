import type { AiProvider, CloudProvider } from "../config/env";
import { getDeploymentPresentation } from "../config/deploymentPresentation";

type DeploymentBadgeProps = {
  readonly cloudProvider: CloudProvider;
  readonly aiProvider: AiProvider;
  readonly cloudRegion: string;
};

/** Neutral generic cloud mark — not an Azure or AWS trademark. */
function NeutralCloudIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M7.5 18h9.25a3.75 3.75 0 0 0 .4-7.48 5.25 5.25 0 0 0-10.05-1.2A3.5 3.5 0 0 0 7.5 18z" />
    </svg>
  );
}

const summaryClassName =
  "inline-flex cursor-pointer list-none items-center gap-1 rounded-full border border-slate-300 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600 shadow-sm marker:content-none [&::-webkit-details-marker]:hidden";

const detailLinkClassName =
  "rounded-sm text-slate-600 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500";

/**
 * Owner-UI deployment indicator. Presentation metadata only —
 * does not grant or imply Platform Owner authorization.
 */
export function DeploymentBadge({
  cloudProvider,
  aiProvider,
  cloudRegion,
}: DeploymentBadgeProps) {
  const presentation = getDeploymentPresentation({
    cloudProvider,
    aiProvider,
    cloudRegion,
  });

  return (
    <details className="relative inline-flex min-w-0" data-testid="deployment-badge">
      <summary
        className={summaryClassName}
        aria-label={`Deployment: ${presentation.cloudLabel}. Expand for AI provider and region. Informational only; not authorization.`}
      >
        <NeutralCloudIcon className="h-3.5 w-3.5 shrink-0 text-slate-500" />
        <span data-testid="deployment-cloud-label">{presentation.cloudLabel}</span>
      </summary>
      <div
        className="absolute end-0 top-full z-10 mt-1 w-max max-w-[min(18rem,calc(100vw-2rem))] rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-600 shadow-md"
        data-testid="deployment-details"
      >
        <dl className="space-y-1">
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-slate-500">Cloud:</dt>
            <dd>
              <a
                href={presentation.cloudUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={detailLinkClassName}
                aria-label={`${presentation.cloudLabel} official site (opens in a new tab)`}
                data-testid="deployment-cloud-link"
              >
                {presentation.cloudLabel}
              </a>
            </dd>
          </div>
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-slate-500">AI:</dt>
            <dd>
              <a
                href={presentation.aiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={detailLinkClassName}
                aria-label={`${presentation.aiLabel} official product page (opens in a new tab)`}
                data-testid="deployment-ai-link"
              >
                {presentation.aiLabel}
              </a>
            </dd>
          </div>
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-slate-500">Region:</dt>
            <dd data-testid="deployment-region">{presentation.cloudRegion}</dd>
          </div>
        </dl>
        <p className="mt-1.5 text-[0.65rem] leading-snug text-slate-400">
          Informational reference only. Not sponsorship, endorsement, or authorization.
        </p>
      </div>
    </details>
  );
}
