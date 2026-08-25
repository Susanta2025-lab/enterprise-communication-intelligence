import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { Button } from "./ui/button";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const { displayName, logout, error, interactionInProgress } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl min-w-0 flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Enterprise Communication Intelligence
            </p>
            <h1 className="text-lg font-semibold">ECI Platform</h1>
          </div>
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            {displayName ? (
              <p className="min-w-0 break-words text-sm text-slate-600" data-testid="signed-in-account">
                Signed in as {displayName}
              </p>
            ) : (
              <p className="text-sm text-slate-600">Signed in</p>
            )}
            <Button className="w-full sm:w-auto" onClick={() => void logout()} disabled={interactionInProgress}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-6xl min-w-0 px-4 py-8 sm:px-6">
        {error ? (
          <p role="alert" className="mb-4 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {children}
      </main>
    </div>
  );
}
