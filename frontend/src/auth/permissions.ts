export const ECI_PERMISSIONS = [
  "communications:read",
  "communications:analyze",
  "communications:connect",
  "communications:workflow",
  "communications:send",
] as const;

export type EciPermission = (typeof ECI_PERMISSIONS)[number];

const ECI_PERMISSION_SET: ReadonlySet<string> = new Set(ECI_PERMISSIONS);

export function isEciPermission(value: string): value is EciPermission {
  return ECI_PERMISSION_SET.has(value);
}

export function permissionFromScopeValue(value: string): EciPermission | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const name = trimmed.includes("/") ? (trimmed.split("/").at(-1) ?? "") : trimmed;
  if (!isEciPermission(name)) {
    return null;
  }
  return name;
}

export function parseScopeClaim(scp: string | null | undefined): readonly EciPermission[] {
  if (!scp) {
    return [];
  }
  const permissions: EciPermission[] = [];
  const seen = new Set<EciPermission>();
  for (const part of scp.split(/\s+/)) {
    const permission = permissionFromScopeValue(part);
    if (permission && !seen.has(permission)) {
      seen.add(permission);
      permissions.push(permission);
    }
  }
  return permissions;
}

export function hasPermission(
  permissions: readonly string[],
  required: EciPermission,
): boolean {
  return permissions.some((permission) => permissionFromScopeValue(permission) === required);
}

export function hasAllPermissions(
  permissions: readonly string[],
  required: readonly EciPermission[],
): boolean {
  return required.every((permission) => hasPermission(permissions, permission));
}
