import { createContext, useContext } from "react";

import type { CurrentUserState } from "./currentUserState";

export const CurrentUserContext = createContext<CurrentUserState | null>(null);

export function useCurrentUser(): CurrentUserState {
  const state = useContext(CurrentUserContext);
  if (state === null) {
    throw new Error("useCurrentUser must be used within CurrentUserProvider.");
  }
  return state;
}
