import type { AiProvider, CloudProvider } from "./env";

export type DeploymentPresentation = {
  readonly cloudProvider: CloudProvider;
  readonly aiProvider: AiProvider;
  readonly cloudRegion: string;
  readonly cloudLabel: string;
  readonly cloudUrl: string;
  readonly aiLabel: string;
  readonly aiUrl: string;
};

const PRESENTATION: Record<
  CloudProvider,
  {
    readonly cloudLabel: string;
    readonly cloudUrl: string;
    readonly aiLabel: string;
    readonly aiUrl: string;
  }
> = {
  azure: {
    cloudLabel: "Azure",
    cloudUrl: "https://azure.microsoft.com/",
    aiLabel: "Microsoft Foundry",
    aiUrl: "https://azure.microsoft.com/products/ai-foundry/",
  },
  aws: {
    cloudLabel: "AWS",
    cloudUrl: "https://aws.amazon.com/",
    aiLabel: "Amazon Bedrock",
    aiUrl: "https://aws.amazon.com/bedrock/",
  },
};

/**
 * Safe display labels and official vendor reference URLs for owner UI.
 * Presentation only — not authorization or sponsorship signals.
 */
export function getDeploymentPresentation(input: {
  readonly cloudProvider: CloudProvider;
  readonly aiProvider: AiProvider;
  readonly cloudRegion: string;
}): DeploymentPresentation {
  const base = PRESENTATION[input.cloudProvider];
  return Object.freeze({
    cloudProvider: input.cloudProvider,
    aiProvider: input.aiProvider,
    cloudRegion: input.cloudRegion,
    cloudLabel: base.cloudLabel,
    cloudUrl: base.cloudUrl,
    aiLabel: base.aiLabel,
    aiUrl: base.aiUrl,
  });
}
