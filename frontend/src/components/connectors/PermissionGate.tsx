import type { ReactNode } from "react";

import { useAuth } from "../../auth/AuthContext";
import { hasPermission, type EciPermission } from "../../auth/permissions";

type PermissionGateProps = {
  permission: EciPermission;
  children: ReactNode;
  fallback?: ReactNode;
};

export function PermissionGate({ permission, children, fallback = null }: PermissionGateProps) {
  const { permissions } = useAuth();
  if (!hasPermission(permissions, permission)) {
    return fallback;
  }
  return children;
}
