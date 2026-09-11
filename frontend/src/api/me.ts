export const ME_PATH = "/api/v1/me";

export type ApplicationRole = "user" | "owner";

export type MeResponse = {
  application_role: ApplicationRole;
  is_owner: boolean;
};

export function parseMeResponse(payload: unknown): MeResponse | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  const role = body.application_role;
  const isOwner = body.is_owner;
  if (role !== "user" && role !== "owner") {
    return null;
  }
  if (typeof isOwner !== "boolean") {
    return null;
  }
  if (isOwner !== (role === "owner")) {
    return null;
  }
  return { application_role: role, is_owner: isOwner };
}
