import type { ApplicationRole } from "../api/me";

export type CurrentUserStatus = "anonymous" | "loading" | "ready" | "error";

export type CurrentUserState = {
  status: CurrentUserStatus;
  applicationRole: ApplicationRole | null;
  isOwner: boolean;
};

export const ANONYMOUS_CURRENT_USER: CurrentUserState = {
  status: "anonymous",
  applicationRole: null,
  isOwner: false,
};

export const LOADING_CURRENT_USER: CurrentUserState = {
  status: "loading",
  applicationRole: null,
  isOwner: false,
};

export const ERROR_CURRENT_USER: CurrentUserState = {
  status: "error",
  applicationRole: null,
  isOwner: false,
};
