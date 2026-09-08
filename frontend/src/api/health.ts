export const HEALTH_PATH = "/api/v1/health";

export type AiImageInputCapability = "available" | "unavailable";

export type PlatformHealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
  attachment_scanner: string;
  ai_image_input: AiImageInputCapability | string;
};

export function isAiImageInputAvailable(
  value: PlatformHealthResponse["ai_image_input"] | null | undefined,
): boolean {
  return value === "available";
}
